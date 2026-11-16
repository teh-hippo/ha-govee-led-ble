"""Coordinator control-state snapshot and restoration tests."""

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES, MUSIC_MODE_SLUGS, ReadDomain, device_profile
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent, async_control_intent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import DEFAULT_REFRESH_REQUEST, RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, StatusDomain
from custom_components.ha_govee_led_ble.effect_commands import build_h617a_diy_activation
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_blank_screen,
    build_brightness,
    build_power,
    build_scene_activation,
    table_kelvin_rgb,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, normalize_kelvin, parse_static_write
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.scenes import MODEL_SCENES, scene_selector_code
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
from custom_components.ha_govee_led_ble.video_applicability import video_identity_fields
from tests.coordinator_test_support import _CONFIGURATION_URL, _c, _packet

M = "custom_components.ha_govee_led_ble.coordinator"


async def test_late_layout_qualification_permanently_discards_incompatible_history(hass, monkeypatch):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H705A", configuration_url=None)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    coord._pre_mode_snapshot = PriorControlState("colour", True, 37, (10, 20, 30))
    coord._pre_mode_profile = coord.profile
    coord._pre_mode_needs_qualification = True
    coord._client = _c(write_gatt_char=AsyncMock())
    coord._notification_token = object()
    coord.pact_code = 2
    coord._resolve_device_profile()

    async def receive_count(*args, **kwargs):
        coord._apply_physical_ic_count(
            SimpleNamespace(domain=SimpleNamespace(name="physical_ic_count"), body=SimpleNamespace(count=36))
        )
        coord._mark_received(StatusDomain.PHYSICAL_IC_COUNT, "physical_ic_count")

    monkeypatch.setattr(coord, "_async_write_packet", AsyncMock(side_effect=receive_count))
    assert await coord._read_configured_strings(coord._client, deadline=time.monotonic() + 1)
    assert coord._physical_ic_count_confirmed and coord._configured_strings_confirmed
    assert coord._pre_mode_snapshot is None
    coord.pact_code = 1
    coord._resolve_device_profile()
    assert not coord._static_history_profile_current()


@pytest.mark.parametrize(
    ("confirmed", "physical_count", "eligible"),
    [(False, 36, False), (True, 36, True), (True, 37, False)],
)
def test_suspended_history_requires_qualified_physical_geometry(hass, confirmed, physical_count, eligible):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H705A", configuration_url=None)
    original = coord.profile
    coord._pre_mode_snapshot = PriorControlState("colour", True, 20, (10, 20, 30))
    coord._pre_mode_profile = original
    coord._pre_mode_needs_qualification = True
    coord._physical_ic_count_confirmed = coord._configured_strings_confirmed = confirmed
    coord.profile = replace(original, physical_ic_count=physical_count)
    assert coord.profile.segment_count == original.segment_count
    assert coord._static_history_profile_current() is eligible
    assert (coord._pre_mode_snapshot is None) is (confirmed and physical_count != original.physical_ic_count)


@pytest.mark.parametrize(
    ("initially_on", "kelvin", "retry_selector", "release_between"),
    [
        (False, None, False, False),
        (True, None, False, False),
        (False, 5000, False, False),
        (True, 5000, False, False),
        pytest.param(True, None, True, False, id="selector-retry"),
        pytest.param(False, None, False, True, id="released-rgb"),
        pytest.param(True, 5000, False, True, id="released-kelvin"),
    ],
)
async def test_write_only_static_effect_off_round_trip(
    hass, monkeypatch, virtual_clock, initially_on, kelvin, retry_selector, release_between
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H601C", configuration_url=None)
    client = _c(write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coord._client = client
    coord._present = True
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic()
    if release_between:
        client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)

    async def connect():
        client.is_connected = True
        coord._client = client
        if coord._notification_token is None:
            coord._notification_token = object()
            coord._notify_started_monotonic = time.monotonic()
        return client

    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(side_effect=connect))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    physical = {"on": False, "level": None, "rgb": None, "kelvin": None}
    selector_failed = False

    async def radio(_uuid, packet, **_kwargs):
        nonlocal selector_failed
        if packet[:2] == b"\x33\x01":
            physical["on"] = bool(packet[2])
        elif packet[:2] == b"\x33\x04":
            physical["level"] = packet[2]
        elif packet[:3] == b"\x33\x05\x0d":
            static = parse_static_write(packet, coord.model, profile=coord.profile)
            assert static is not None
            physical["rgb"] = static.rgb or static.kelvin_companion_rgb
            physical["kelvin"] = static.kelvin
        elif packet[:3] == b"\x33\x05\x04":
            physical["rgb"] = (255, 0, 0)
            physical["kelvin"] = None
            if retry_selector and not selector_failed:
                selector_failed = True
                raise BleakError("Connection lost during selector delivery")

    client.write_gatt_char.side_effect = radio
    light = GoveeBLELight(coord)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])

    async def control(**attrs):
        await hass.services.async_call("light", "turn_on", {"entity_id": light.entity_id, **attrs}, blocking=True)

    if not initially_on and kelvin is None:
        with pytest.raises(HomeAssistantError) as error:
            await control(effect="Morning", brightness=200)
        assert error.value.translation_key == "recovery_not_ready"
        client.write_gatt_char.assert_not_awaited()
    await control(**({"rgb_color": [36, 72, 108]} if kelvin is None else {"color_temp_kelvin": kelvin}), brightness=102)
    if initially_on and kelvin is None:
        coord._clear_client_state(client)
        coord._client = client
        coord._notification_token = object()
        physical["on"] = False
        await control(rgb_color=[36, 72, 108], brightness=102)
        assert physical["on"]
    if not initially_on:
        await hass.services.async_call("light", "turn_off", {"entity_id": light.entity_id}, blocking=True)
    before = dict(physical)
    await control(effect="Morning")
    if release_between:
        await coord._async_disconnect_on_timeout(coord._disconnect_generation)
    await control(effect="Dusk")
    if release_between:
        await coord._async_disconnect_on_timeout(coord._disconnect_generation)
    assert physical["rgb"] != before["rgb"]
    await control(effect="off")
    assert physical == before
    assert selector_failed is retry_selector
    assert not any(call.args[1][0] == 0xAA for call in client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("field", ["brightness_pct", "is_on"])
async def test_interrupted_write_only_controls_cannot_publish_rolled_back_baseline(
    hass, monkeypatch, virtual_clock, field
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H601C", configuration_url=None)
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    light = GoveeBLELight(coord)
    monkeypatch.setattr(light, "_notify_state_changed", lambda: None)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    sent, resume, queued = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pause = False

    async def radio(_uuid, packet, **_kwargs):
        if pause and packet[:2] == (b"\x33\x04" if field == "brightness_pct" else b"\x33\x01"):
            sent.set()
            await resume.wait()

    client.write_gatt_char.side_effect = radio
    await light.async_turn_on(rgb_color=(36, 72, 108), brightness=102)
    if field == "is_on":
        await light.async_turn_off()
    pause = True
    first = asyncio.create_task(
        light.async_turn_on(effect="Morning", **({"brightness": 204} if field == "brightness_pct" else {}))
    )
    await sent.wait()
    invalidate = coord._control_arbiter.invalidate_previews

    def invalidate_and_signal():
        invalidate()
        queued.set()

    monkeypatch.setattr(coord._control_arbiter, "invalidate_previews", invalidate_and_signal)

    async def foreground():
        async with async_control_intent(coord, ControlIntent.APPLY):
            pass

    other = asyncio.create_task(foreground())
    await queued.wait()
    resume.set()
    with pytest.raises(HomeAssistantError):
        await first
    await other
    pause = False
    before = client.write_gatt_char.await_count
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(effect="Dusk")
    assert error.value.translation_key == "recovery_not_ready"
    assert client.write_gatt_char.await_count == before
    await light.async_turn_on(rgb_color=(36, 72, 108), brightness=204)
    await light.async_turn_on(effect="Dusk")
    assert coord._pre_mode_snapshot is not None
    assert coord._pre_mode_snapshot.brightness_pct == 80 and coord._pre_mode_snapshot.is_on


@pytest.mark.parametrize(
    ("model", "external_kelvin", "initially_on", "rendered"),
    [
        ("H6072", 5000, True, (255, 255, 255)),
        ("H6076", None, True, (255, 185, 105)),
        ("H6076", None, False, (255, 146, 39)),
    ],
)
async def test_native_white_scene_off_uses_supported_observations(
    hass, monkeypatch, virtual_clock, model, external_kelvin, initially_on, rendered
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    if model == "H6072":
        coord.profile = device_profile(model, 2, 1, firmware="2.04.10", hardware="3.02.00")
    monkeypatch.setattr(coord, "_authorization_profile", lambda: coord.profile)
    monkeypatch.setattr(coord, "_reconcile_authorization", lambda: None)
    monkeypatch.setattr(coord, "async_prepare_identity_gated_control", AsyncMock(return_value=lambda: None))
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    coord._notification_token = object()
    coord._notify_started_monotonic = virtual_clock.virtual_time()
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    light = GoveeBLELight(coord)
    monkeypatch.setattr(light, "_notify_state_changed", lambda: None)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    count = coord.profile.segment_count
    physical = {"on": False, "level": 100, "kelvin": 0, "colours": [(10, 20, 30)] * count, "scene": None}

    def reply(domain, values):
        coord._notify_callback(None, bytearray(_packet(0xAA, domain, values)))

    async def radio(_uuid, packet, **_kwargs):
        if packet[0] == 0xAA:
            if packet[1] == 1:
                reply(1, [int(physical["on"])])
            elif packet[1] == 4:
                reply(4, [physical["level"]])
            elif packet[1] == 5:
                reply(
                    5,
                    [4, *physical["scene"]]
                    if physical["scene"]
                    else [0x15, 0, physical["kelvin"] >> 8, physical["kelvin"] & 255],
                )
            elif packet[1] == 0xA5:
                for group in range(1, coord.profile.segment_group_count + 1):
                    start = (group - 1) * coord.profile.segment_group_size
                    reply(
                        0xA5,
                        [
                            group,
                            *(
                                value
                                for rgb in physical["colours"][start : start + coord.profile.segment_group_size]
                                for value in (100, *rgb)
                            ),
                        ],
                    )
        elif packet[:2] == b"\x33\x01":
            physical["on"] = bool(packet[2])
        elif packet[:2] == b"\x33\x04":
            physical["level"] = packet[2]
        elif packet[:3] == b"\x33\x05\x04":
            physical["scene"] = list(packet[3:5])
            physical["colours"] = [(255, 0, 0)] * count
        elif (static := parse_static_write(packet, model, profile=coord.profile)) is not None:
            physical["scene"] = None
            if static.kelvin is not None:
                physical["kelvin"] = static.kelvin
                physical["colours"] = [rendered] * count
        pending = coord._upload_ack
        if pending is not None and not pending.future.done():
            coord._notify_callback(
                None,
                bytearray(
                    _packet(pending.protocol, pending.subtype, [0] if pending.mode is None else [pending.mode, 0])
                ),
            )

    async def gradual(control, enabled):
        assert control == "gradual"
        coord.static_gradual = enabled

    monkeypatch.setattr(coord, "async_set_boolean_control", gradual)
    client.write_gatt_char.side_effect = radio
    await light.async_turn_on(color_temp_kelvin=3000, brightness=128)
    if external_kelvin is not None:
        coord._expected_state.clear()
        physical["kelvin"] = external_kelvin
    if not initially_on:
        await light.async_turn_off()
    expected_kelvin = external_kelvin or 3000
    scene = next(entry.display_label for entry in light._selector_entries() if entry.source == "scene")
    await light.async_turn_on(effect=scene)
    assert coord._pre_mode_snapshot is not None
    assert coord._pre_mode_snapshot.static_segment_kelvin(coord.profile) == (expected_kelvin,) * count
    await light.async_turn_on(effect="off")
    assert physical["on"] is initially_on
    assert physical["kelvin"] == expected_kelvin
    assert physical["colours"] == [rendered] * count


async def test_whole_device_revision_keeps_its_scalar_effect_stop(hass, monkeypatch, virtual_clock):
    from tests.test_h60a_protocol import bulk_frames

    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60A6", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(coord, "_authorization_profile", MagicMock(return_value=coord.profile))
    physical = None

    async def radio(_uuid, packet, **_kwargs):
        nonlocal physical
        if packet[0] == 0xAC:
            for response in bulk_frames(bytes.fromhex("01010105041500000030020101")):
                coord._notify_callback(None, bytearray(response))
        elif packet[:2] == b"\xaa\x01":
            coord._notify_callback(None, bytearray(_packet(0xAA, 1, [1])))
        pending = coord._upload_ack
        if pending is not None and not pending.future.done():
            coord._notify_callback(
                None,
                bytearray(
                    _packet(pending.protocol, pending.subtype, [0] if pending.mode is None else [pending.mode, 0])
                ),
            )
        if packet[:3] == b"\x33\x05\x0d":
            physical = tuple(packet[3:6])

    client.write_gatt_char.side_effect = radio
    original = (36, 72, 108)
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic() - 1
    await coord.send_command(build_power(True, coord.model))
    await coord.send_command(build_brightness(40, coord.model, profile=coord.profile))
    await coord.send_command(build_color_rgb(*original, coord.model, profile=coord.profile))
    for _ in range(2):
        await coord.async_apply_native_scene("rainbow", verify=False)
        physical = (255, 0, 0)
        await coord.async_restore_pre_mode()
        assert physical == original
        assert coord.color_mode is ParsedMode.COLOUR


def source_recovery_wire(hass, monkeypatch, model):
    from tests.test_h60a_protocol import bulk_frames

    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile(model, 1, 2 if model == "H60A6" else 1)
    coord.pact_type, coord.pact_code = 1, 2 if model == "H60A6" else 1
    coord._confirmed_identity_fields.add("pact")
    if model == "H607C":
        coord._h607c_marker_seen = True
        coord._h607c_marker_pact = (1, 1)
        monkeypatch.setattr(coord, "_refresh_h607c_advertisements", lambda: None)
    coord._resolve_device_profile()
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic() - 1
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(coord, "_authorization_profile", MagicMock(return_value=coord.profile))
    monkeypatch.setattr(coord, "_async_supersede_effect_preview", AsyncMock())
    colours = [(0, 0, 0)] * coord.profile.segment_count
    levels = [50] * coord.profile.segment_count
    packets = []
    source_flags = {0: False, 1: True}
    physical = {
        "master": 50,
        "powered": True,
        "gradual": False,
        "scene": None,
        "fail_colour": False,
        "colours": colours,
        "levels": levels,
        "packets": packets,
        "source_flags": source_flags,
    }

    async def radio(_uuid, packet, **_kwargs):
        packets.append(packet)
        if packet[0] == 0x33:
            if packet[1] == 0x01:
                physical["powered"] = bool(packet[2])
            elif packet[1] == 0x04:
                physical["master"] = packet[2]
            elif packet[1:3] == b"\x05\x04":
                physical["scene"] = list(packet[3:5])
            elif model == "H1771" and packet[1] == 0x36:
                source_flags[packet[2]] = bool(packet[3])
            elif model == "H1771" and packet[1] == 0xA3:
                physical["gradual"] = bool(packet[2])
            static = parse_static_write(packet, model, profile=coord.profile)
            if static is not None:
                physical["scene"] = None
                if physical["fail_colour"] and static.rgb == (2, 20, 40):
                    raise RuntimeError("Injected delivery failure")
                mask = static.segment_mask if static.segment_mask is not None else coord.profile.whole_device_mask
                for index in range(len(colours)):
                    if mask & (1 << index):
                        if static.rgb is not None:
                            colours[index] = static.rgb
                        if static.brightness_pct is not None:
                            levels[index] = static.brightness_pct
            return
        if packet[0] == 0xAC:
            if model == "H1771":
                flags = int(physical["powered"]) | int(source_flags[0]) << 1 | int(source_flags[1]) << 2
                coord._notify_callback(
                    None,
                    bytearray(
                        _packet(
                            0xAC, 0, [1, 0, 10, 3, 0, 0x36, 1, flags, 0xA3, 1, int(physical["gradual"]), 0x41, 2, 0, 0]
                        )
                    ),
                )
                return
            mode = "050304" + bytes(physical["scene"]).hex() if physical["scene"] is not None else "050415000000"
            for response in bulk_frames(bytes.fromhex(f"0101{int(physical['powered']):02x}{mode}30020101")):
                coord._notify_callback(None, bytearray(response))
            return
        command = packet[1]
        if command == 0xA5:
            assert coord.profile.can_read(ReadDomain.SEGMENTS)
            offset = (packet[2] - 1) * coord.profile.segment_group_size
            records = [
                value
                for index in range(offset, min(offset + coord.profile.segment_group_size, len(colours)))
                for value in (levels[index], *colours[index])
            ]
            response = _packet(0xAA, command, [packet[2], *records])
        elif command == 0x05:
            body = (
                [0x04, *physical["scene"]]
                if physical["scene"] is not None
                else [0x0D if model == "H1771" else 0x15, int(model == "H607C"), 0, 0, 0, 0]
            )
            response = _packet(0xAA, command, body)
        elif command == 0x01:
            response = _packet(0xAA, command, [int(physical["powered"])])
        elif command == 0x04:
            response = _packet(0xAA, command, [physical["master"]])
        elif command == 0x33:
            response = _packet(0xAA, command, [0x11])
        elif command == 0x36:
            response = _packet(0xAA, command, [1, 1, 1])
        elif command == 0x07:
            response = _packet(0xAA, command, [8, 37, 7])
        elif command == 0xA3:
            response = _packet(0xAA, command, [1])
        elif command == 0x41:
            response = _packet(0xAA, command, [1, 2])
        else:
            return
        coord._notify_callback(None, bytearray(response))

    client.write_gatt_char.side_effect = radio
    return coord, physical


@pytest.mark.parametrize(
    ("model", "fail_colour"),
    [("H6046", False), ("H607C", False), ("H607C", True), ("H60B2", False), ("H60A6", False), ("H1771", False)],
)
async def test_source_scene_stop_preserves_authored_layout_over_actual_read_domains(
    hass, monkeypatch, virtual_clock, model, fail_colour
):
    coord, physical = source_recovery_wire(hass, monkeypatch, model)
    colours, levels, packets, source_flags = (
        physical["colours"],
        physical["levels"],
        physical["packets"],
        physical["source_flags"],
    )
    physical["fail_colour"] = fail_colour
    await coord.send_command(build_brightness(40, model, profile=coord.profile))
    authored = [(index + 1, 20, 40) for index in range(len(colours))]
    if fail_colour:
        with pytest.raises(RuntimeError, match="Injected delivery failure"):
            await coord.async_paint_segments([([index], rgb) for index, rgb in enumerate(authored, 1)])
        assert coord.capture_effect_control_state().segment_colors is None
        physical["fail_colour"] = False
    await coord.async_paint_segments([([index], rgb) for index, rgb in enumerate(authored, 1)])
    if not coord.profile.can_read(ReadDomain.SEGMENTS):
        assert await coord.refresh_state(RefreshRequest(refresh_all=True, query_segments=False))
        incomplete = coord.capture_effect_control_state()
        assert incomplete.segment_colors == tuple(authored)
        assert incomplete.segment_brightness is None
        attempts = len(packets)
        assert not await coord.async_restore_effect_control_state(incomplete, overwritten_diy_code=None)
        assert len(packets) == attempts
    if coord.profile.supports_segment_brightness:
        await coord.async_set_segment_brightness(list(range(1, len(colours) + 1)), 60)
    result = await coord.refresh_state(
        RefreshRequest(refresh_all=True, query_segments=coord.profile.can_read(ReadDomain.SEGMENTS))
    )
    assert result
    before = coord.capture_effect_control_state()
    assert before.segment_colors == tuple(authored)
    assert before.static_segment_kelvin(coord.profile) is not None
    if model == "H60A6":
        from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state

        assert not coord.profile.can_read(ReadDomain.BRIGHTNESS)
        assert await async_prepare_effect_control_state(coord, require_restorable_static=True)
    expected_flags = dict(source_flags)
    if not coord.profile.can_read(ReadDomain.SEGMENTS):
        from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state

        scene_name = next(
            name for name, scene in MODEL_SCENES[model].items() if scene.scene_type == 0 and scene.speed is None
        )
        await coord.async_apply_native_scene(scene_name, verify=False)
        baseline = coord._pre_mode_snapshot
        assert baseline is not None and not baseline.static_colour_observed
        attempts = len(packets)
        with pytest.raises(RuntimeError, match="observations"):
            await async_prepare_effect_control_state(coord, require_restorable_static=True)
        assert not any(packet[0] == 0x33 for packet in packets[attempts:])
        assert coord._pre_mode_snapshot is baseline
    else:
        await coord.send_command(build_scene_activation(model, 1, profile=coord.profile))
    if model == "H1771":
        source_flags.update({0: True, 1: False})
    colours[:] = [(255, 0, 0)] * len(colours)
    await coord.async_restore_pre_mode()
    assert colours == authored
    assert tuple(levels) == before.segment_brightness
    assert physical["master"] == 40
    assert source_flags == expected_flags
    assert coord.segment_state_source == ("observed" if coord.profile.can_read(ReadDomain.SEGMENTS) else "optimistic")
    if not coord.profile.can_read(ReadDomain.SEGMENTS):
        assert not any(packet[:2] == b"\xaa\xa5" for packet in packets)
        from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state

        with pytest.raises(RuntimeError, match="observ"):
            await async_prepare_effect_control_state(coord, require_restorable_static=True)


@pytest.mark.parametrize(
    "model,query,reply",
    [("H60B2", b"\xaa\x36", (0x36, [0, 1, 0])), ("H607C", b"\xaa\x07\x08", (0x07, [8, 37, 0x85]))],
)
@pytest.mark.parametrize("fresh", [True, False])
async def test_source_recovery_uses_independent_register_and_requires_fresh_flags(
    hass, monkeypatch, virtual_clock, model, query, reply, fresh
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile(model, 1, 1)
    coord.is_on = True
    coord._notification_token = object()
    coord._notify_started_monotonic = time.monotonic()
    expected = {source.control: index % 2 == 0 for index, source in enumerate(coord.profile.light_sources)}
    coord.boolean_control_state.update(expected)
    coord._field_received_at.update({f"boolean_{control}": -1 for control in expected})
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    monkeypatch.setattr(coord, "_async_restore_effect_appearance", AsyncMock(return_value=True))
    bulk = AsyncMock(side_effect=AssertionError("Independent source state is not a bulk observation"))
    monkeypatch.setattr(coord, "_async_read_bulk_status", bulk)

    async def respond(_uuid, packet, **kwargs):
        assert packet.startswith(query)
        if fresh:
            coord._notify_callback(None, bytearray(_packet(0xAA, reply[0], reply[1])))

    async def set_control(control, enabled):
        coord.boolean_control_state[control] = enabled

    client.write_gatt_char.side_effect = respond
    setter = AsyncMock(side_effect=set_control)
    monkeypatch.setattr(coord, "async_set_boolean_control", setter)
    state = PriorControlState("scene", True, 50, (1, 2, 3), **expected)
    assert await coord.async_restore_effect_control_state(state, overwritten_diy_code=None) is fresh
    bulk.assert_not_awaited()
    if fresh:
        assert {item.args for item in setter.await_args_list} == set(expected.items())
        assert all(coord._field_revisions[f"boolean_{control}"] > 0 for control in expected)
    else:
        setter.assert_not_awaited()


@pytest.mark.parametrize("six_zones", [False, True])
@pytest.mark.parametrize("missing", [False, True])
async def test_relative_brightness_recovery_requires_all_declared_zones(h6199, monkeypatch, six_zones, missing):
    module = "custom_components.ha_govee_led_ble.coordinator_recovery"
    zones = ("left", "top", "right", "bottom") + (("strip_left", "strip_right") if six_zones else ())
    h6199.profile = replace(h6199.profile, video_brightness_zones=zones)
    values = {f"relative_brightness_{zone}": 40 for zone in zones}
    if missing:
        values[f"relative_brightness_{zones[-1]}"] = None
    state = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=20,
        rgb_color=(1, 2, 3),
        video_restore_controls=("relative_brightness",),
        **values,
    )
    monkeypatch.setattr(
        f"{module}.video_control_states", lambda *args: {"relative_brightness": CapabilityState.SUPPORTED}
    )
    apply = AsyncMock(return_value=True)
    monkeypatch.setattr(f"{module}.apply_relative_brightness", apply)
    permitted, complete = await h6199._restore_video_controls(state)
    assert complete is (not missing)
    if missing:
        apply.assert_not_awaited()
        assert "relative_brightness" not in permitted
    else:
        apply.assert_awaited_once_with(h6199, (40,) * len(zones))


@pytest.mark.parametrize(
    "outcome",
    (
        "match",
        "missing",
        "verification_missing",
        "cancelled",
        "sibling_changed",
        "subscription_changed",
        "write_failed",
        "write_cancelled",
    ),
)
@pytest.mark.parametrize("entrypoint", ("setting", "source"))
async def test_h6046_bar_write_preserves_fresh_sibling_and_unknown_flags(
    hass, monkeypatch, virtual_clock, outcome, entrypoint
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 2, 1
    coord._resolve_device_profile()
    coord._notify_started_monotonic = virtual_clock.virtual_time()
    coord._notification_token = object()
    coord.is_on = True
    coord._mark_received(StatusDomain.POWER, "is_on")
    coord.boolean_control_state = {"left_bar_enabled": False, "right_bar_enabled": False}
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    queried = 0

    async def respond(_uuid, packet, **kwargs):
        nonlocal queried
        if packet[:2] == b"\x33\x33":
            if outcome == "write_failed":
                assert not coord.boolean_control_state
                assert not any(field.startswith("boolean_") for field in coord._field_received_at)
                assert not coord._source_power_observation_generation
                raise ValueError("Physical write failed")
            if outcome == "write_cancelled":
                coord._notify_callback(None, bytearray(_packet(0xAA, 0x33, [0x81])))
                raise asyncio.CancelledError
        if packet[:2] == b"\xaa\x33":
            queried += 1
            if outcome == "cancelled":
                raise asyncio.CancelledError
            if outcome == "missing" or (outcome == "verification_missing" and queried == 2):
                return
            flags = 0x90 if queried == 1 else 0x81 if outcome == "sibling_changed" else 0x91
            coord._notify_callback(None, bytearray(_packet(0xAA, 0x33, [flags])))
            if outcome == "subscription_changed":
                coord._notification_token = object()

    client.write_gatt_char.side_effect = respond

    async def set_control():
        if entrypoint == "source":
            await GoveeBLESourceLight(coord, "left_bar").async_turn_on()
        else:
            await coord.async_set_boolean_control("left_bar_enabled", True)

    if outcome == "match":
        await set_control()
        assert coord.boolean_control_state == {"left_bar_enabled": True, "right_bar_enabled": True}
    elif outcome in {"cancelled", "write_cancelled"}:
        with pytest.raises(asyncio.CancelledError):
            await set_control()
    else:
        with pytest.raises(HomeAssistantError if entrypoint == "source" else ValueError):
            await set_control()
    if outcome in {"sibling_changed", "write_cancelled"}:
        assert coord.boolean_control_state == {"left_bar_enabled": True, "right_bar_enabled": False}
        assert coord._field_received_at["boolean_left_bar_enabled"] >= coord._notify_started_monotonic
        assert coord._source_power_observation_generation["boolean_left_bar_enabled"] == (
            coord._power_write_generation,
            coord._profile_generation,
        )
    elif outcome == "write_failed":
        assert not coord.boolean_control_state
        assert not coord._source_power_observation_generation
    writes = [item.args[1] for item in client.write_gatt_char.await_args_list]
    if outcome in {"missing", "subscription_changed", "cancelled"}:
        assert writes == [_packet(0xAA, 0x33, [])]
    elif outcome in {"write_failed", "write_cancelled"}:
        assert writes == [_packet(0xAA, 0x33, []), _packet(0x33, 0x33, [0x91])]
    else:
        assert writes == [_packet(0xAA, 0x33, []), _packet(0x33, 0x33, [0x91]), _packet(0xAA, 0x33, [])]
    if outcome in {"missing", "verification_missing", "subscription_changed", "cancelled"}:
        client.disconnect.assert_awaited_once()
        assert coord._client is None
    coord._clear_client_state(client)


async def test_h6046_mixed_native_white_revokes_known_rgb_even_when_rendering_is_unchanged(hass):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    coord._client = _c(write_gatt_char=AsyncMock())
    coord._notify_started_monotonic = time.monotonic()
    coord.color_mode = ParsedMode.COLOUR
    coord.segment_colors = [table_kelvin_rgb(2700)] * 10
    coord.segment_state_source = "observed"
    coord._static_rgb_known = True
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x33, [0x11])))
    baseline = coord._field_revisions.get("color_temp_kelvin", 0)
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 0, 0x0A, 0x8C, 0, 0])))
    assert (coord.left_bar_kelvin, coord.right_bar_kelvin) == (2700, 0)
    assert not coord._static_rgb_known
    assert coord._field_revisions.get("color_temp_kelvin", 0) == baseline
    assert coord.color_temp_kelvin_source != "observed"


async def test_h6072_optional_nonzero_kelvin_revokes_rgb_only_recovery(hass):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6072", configuration_url=None)
    coord.profile = device_profile("H6072", 2, 1, firmware="2.04.10", hardware="3.02.00")
    coord.color_mode = ParsedMode.COLOUR
    coord.segment_state_source = "observed"
    coord._static_rgb_known = True
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 1, 0x0C, 0x80])))
    state = coord.capture_effect_control_state()
    assert state.color_temp_kelvin == 3200 and coord.color_temp_kelvin_source == "observed"
    assert not state.static_rgb_known and not coord.profile.static_readback_kelvin
    coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x15, 1, 0, 0])))
    assert coord.color_temp_kelvin == 3200 and not coord._static_rgb_known


@pytest.mark.parametrize(("left", "right"), [(2700, 6500), (1999, 3123)])
def test_h6046_recovery_persists_both_white_points_and_native_power_flags(left, right):

    profile = device_profile("H6046", 1, 1)
    colours = (table_kelvin_rgb(normalize_kelvin(left)),) * 5 + (table_kelvin_rgb(normalize_kelvin(right)),) * 5
    state = PriorControlState(
        mode="colour",
        is_on=False,
        brightness_pct=20,
        rgb_color=(1, 2, 3),
        left_bar_enabled=False,
        right_bar_enabled=True,
        left_bar_kelvin=left,
        right_bar_kelvin=right,
        segment_colors=colours,
        segment_brightness=(50,) * 10,
    )
    restored = PriorControlState.from_dict(state.to_dict())
    assert restored == state and restored.restorable_bar_white(profile)
    assert not replace(restored, left_bar_kelvin=0).restorable_bar_white(profile)
    assert not replace(restored, segment_colors=((1, 2, 3),) * 10).restorable_bar_white(profile)
    legacy = state.to_dict()
    for field in ("left_bar_enabled", "right_bar_enabled", "left_bar_kelvin", "right_bar_kelvin"):
        legacy.pop(field)
    prior = PriorControlState.from_dict(legacy)
    assert prior.left_bar_enabled is None and prior.right_bar_kelvin is None
    assert not prior.restorable_bar_white(profile)


async def test_segmented_kelvin_recovery_normalises_writes_and_expectations_without_rewriting_capture(
    hass, monkeypatch
):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile("H6046", 1, 1)
    coord._client = _c()
    coord._notify_started_monotonic = time.monotonic() - 1
    colours = (table_kelvin_rgb(2000),) * 5 + (table_kelvin_rgb(3100),) * 5
    state = PriorControlState(
        "colour",
        True,
        20,
        (1, 2, 3),
        left_bar_kelvin=1999,
        right_bar_kelvin=3123,
        segment_colors=colours,
        segment_brightness=(50,) * 10,
    )
    send = AsyncMock()
    monkeypatch.setattr(coord, "send_command", send)

    async def refresh(_request):
        coord.is_on = True
        coord.brightness_pct = 20
        coord._mark_received(StatusDomain.BRIGHTNESS, "brightness_pct")
        coord.color_mode = ParsedMode.COLOUR
        coord._field_revisions["color_mode"] = coord._field_revisions.get("color_mode", 0) + 1
        coord.left_bar_kelvin, coord.right_bar_kelvin = 2000, 3100
        coord._observed_mode_write_generation = coord._mode_write_generation
        coord._observed_mode_profile_generation = coord._profile_generation
        coord._field_received_at["color_mode"] = time.monotonic()
        coord._field_received_at["left_bar_kelvin"] = coord._field_received_at["right_bar_kelvin"] = time.monotonic()
        return True

    async def segments():
        coord.segment_colors = list(colours)
        coord.segment_brightness = [50] * 10
        coord.segment_state_source = "observed"
        coord._field_received_at["segment_colors"] = time.monotonic()
        return True

    monkeypatch.setattr(coord, "refresh_state", refresh)
    monkeypatch.setattr(coord, "async_refresh_segments", segments)
    assert await coord._restore_segmented_colour(state, True)
    writes = [
        parsed
        for item in send.await_args_list
        if (parsed := parse_static_write(item.args[0], "H6046", profile=coord.profile)) is not None
        and parsed.kelvin is not None
    ]
    assert [(write.segment_mask, write.kelvin) for write in writes] == [(0x001F, 2000), (0x03E0, 3100)]
    assert (state.left_bar_kelvin, state.right_bar_kelvin) == (1999, 3123)


async def test_native_source_recovery_normalises_its_write_target_not_the_capture(hass, monkeypatch):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile("H60B0", 1, 1)
    flags = {"top_enabled": True, "side_enabled": False, "bottom_enabled": False}
    coord.boolean_control_state.update(flags)
    coord.top_kelvin, coord.bottom_kelvin = 3100, 4000
    coord.bottom_brightness, coord.ripple_speed = 50, 30
    client = _c()
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_async_restore_effect_appearance", AsyncMock(return_value=True))
    monkeypatch.setattr(coord, "_async_read_setting_fields", AsyncMock(return_value=True))

    async def set_value(prepared, **_kwargs):
        field = "ripple_speed" if prepared.attribute == "ripple_speed" else f"{prepared.source}_{prepared.attribute}"
        setattr(coord, field, prepared.value)

    setter = AsyncMock(side_effect=set_value)
    monkeypatch.setattr(coord, "async_apply_source_value", setter)
    state = PriorControlState(
        "scene",
        True,
        20,
        (1, 2, 3),
        top_kelvin=3123,
        bottom_kelvin=1999,
        bottom_brightness=50,
        ripple_speed=30,
        **flags,
    )
    assert await coord.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert [(call.args[0].source, call.args[0].attribute, call.args[0].value) for call in setter.await_args_list] == [
        ("bottom", "kelvin", 2700),
        ("bottom", "brightness", 50),
        ("top", "ripple_speed", 30),
    ]
    assert (state.top_kelvin, state.bottom_kelvin) == (3123, 1999)


async def test_source_colour_recovery_normalises_intents_without_mutating_the_capture(hass, monkeypatch):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=_CONFIGURATION_URL)
    coord.profile = device_profile("H60B0", 1, 1)
    coord._client = _c()
    coord._notify_started_monotonic = time.monotonic() - 1
    intents = {"top": 3123, "side": (1, 2, 3)}
    colours = [(1, 2, 3)] * coord.profile.segment_count
    top = next(source for source in coord.profile.light_sources if source.key == "top")
    for index in top.segments:
        colours[index - 1] = table_kelvin_rgb(3100)
    levels = (50,) * coord.profile.segment_count if coord.profile.supports_segment_brightness else None
    state = PriorControlState(
        "colour",
        True,
        20,
        (1, 2, 3),
        top_kelvin=3123,
        source_static_intents=intents,
        segment_colors=tuple(colours),
        segment_brightness=levels,
    )
    send = AsyncMock()
    monkeypatch.setattr(coord, "send_command", send)

    async def refresh(_request):
        coord.is_on, coord.brightness_pct = True, 20
        coord._mark_received(StatusDomain.BRIGHTNESS, "brightness_pct")
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x05, [0x2C, 0x0C, 0x1C, 30, 0x0A, 0x8C, 50])))
        return True

    async def segments():
        coord.segment_colors = list(colours)
        coord.segment_brightness = list(levels) if levels is not None else [100] * coord.profile.segment_count
        coord.segment_state_source = "observed"
        coord.segment_kelvin = [0] * 8 + [3100]
        coord._field_received_at["segment_colors"] = time.monotonic()
        return True

    monkeypatch.setattr(coord, "refresh_state", refresh)
    monkeypatch.setattr(coord, "async_refresh_segments", segments)
    assert await coord._restore_segmented_colour(state, True)
    writes = [
        parsed
        for item in send.await_args_list
        if (parsed := parse_static_write(item.args[0], "H60B0", profile=coord.profile)) is not None
        and parsed.kelvin is not None
    ]
    assert [(write.segment_mask, write.kelvin) for write in writes] == [
        (sum(1 << (index - 1) for index in top.segments), 3100)
    ]
    assert state.top_kelvin == 3123 and state.source_static_intents == intents


async def test_h6046_swap_is_not_replayed_after_ambiguous_write(hass, monkeypatch):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H6046", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    client = _c(write_gatt_char=AsyncMock(side_effect=RuntimeError("ambiguous swap")))
    coord._client = client
    coord._static_rgb_known = True
    coord.left_bar_kelvin = 2700
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    with pytest.raises(RuntimeError, match="ambiguous"):
        await coord.async_swap_bars()
    assert client.write_gatt_char.await_count == 1
    assert client.write_gatt_char.call_args.args[1] == _packet(0x33, 0x34, [])
    assert not coord._static_rgb_known and coord.left_bar_kelvin is None
    coord._clear_client_state(client)


def test_capture_effect_control_state(coord):
    coord.is_on = True
    coord.brightness_pct = 72
    coord.rgb_color = (1, 2, 3)
    coord.music_sensitivity = 50

    state = coord.capture_effect_control_state()

    assert state == PriorControlState(
        mode="colour",
        music_model="H617A",
        music_parameters={},
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_sensitivity=50,
    )


async def test_restore_effect_control_state_legacy_static_never_flattens(coord):
    state = PriorControlState(
        mode="colour",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
    )

    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is False
    send.assert_not_awaited()
    refresh.assert_not_awaited()


async def test_restore_effect_control_state_cannot_recover_overwritten_diy_slot(coord):
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        diy_code=800,
    )

    with patch.object(coord, "send_command", new_callable=AsyncMock) as send:
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is False
    send.assert_not_awaited()


async def test_restore_effect_control_state_reapplies_model_scene(coord, h6199):
    for coordinator in (coord, h6199):
        effect, scene = next((name, entry) for name, entry in MODEL_SCENES[coordinator.model].items() if entry.param)
        state = PriorControlState(
            mode="scene",
            is_on=True,
            brightness_pct=72,
            rgb_color=(1, 2, 3),
            effect=effect,
        )
        expected = [
            build_power(True, coordinator.model),
            build_brightness(72, coordinator.model),
            build_scene_activation(coordinator.model, scene.code, scene.music_code),
        ]

        with (
            patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
            patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
        ):
            recovered = await coordinator.async_restore_effect_control_state(
                state,
                overwritten_diy_code=-1,
            )

        assert recovered is False  # original authored body/speed is unknown
        assert send.await_args_list == [call(packet) for packet in expected]
        refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=72, scene_code=scene.code))


@pytest.mark.parametrize("with_code", [False, True])
async def test_recovery_rejects_revision_excluded_scene_before_any_write(coord, with_code):
    effect, scene = next(iter(MODEL_SCENES[coord.model].items()))
    coord.profile = replace(coord.profile, scene_codes=frozenset())
    state = PriorControlState("scene", True, 50, (1, 2, 3), effect=effect, scene_code=scene.code if with_code else None)
    with patch.object(coord, "send_command", new_callable=AsyncMock) as send:
        assert not await coord.async_restore_effect_control_state(state, overwritten_diy_code=None)
    send.assert_not_awaited()


async def test_restore_effect_control_state_reapplies_powered_off_state(coord):
    state = PriorControlState(
        mode="colour",
        is_on=False,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
    )

    with (
        patch.object(coord, "send_command", new_callable=AsyncMock) as send,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is False  # power alone cannot recover the missing hidden layout
    send.assert_awaited_once_with(build_power(False), state_values={"is_on": False})
    refresh.assert_awaited_once_with(RefreshRequest(on=False))


@pytest.mark.parametrize("model", ["H617A", "H9999"])
async def test_restore_effect_control_state_reactivates_unmodified_diy_slot(coord, monkeypatch, model):
    monkeypatch.setitem(MODEL_PROFILES, model, coord.profile)
    coord.model = model
    state = PriorControlState(
        mode="custom",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        diy_code=700,
    )

    with (
        patch.object(coord, "send_command", wraps=coord.send_command) as send,
        patch.object(coord, "_ensure_connected", return_value=_c(write_gatt_char=AsyncMock())),
        patch.object(coord, "async_observe_effect", new_callable=AsyncMock, return_value=True) as refresh,
        patch.object(coord, "refresh_state", new=AsyncMock(return_value=True)),
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=800,
        )

    assert recovered is True
    assert send.await_args_list == [
        call(build_power(True, model)),
        call(build_brightness(72, model)),
        call(build_h617a_diy_activation(700), state_values={"diy_code": 700}),
    ]
    refresh.assert_awaited_once_with({"is_on": True, "diy_code": 700})
    assert coord.diy_code == 700


async def test_restore_effect_control_state_reapplies_complete_music_profile(coord):
    from custom_components.ha_govee_led_ble.music_commands import prepare_music_body_writes
    from custom_components.ha_govee_led_ble.music_semantics import music_variant

    body = music_variant(coord.profile, MUSIC_MODE_SLUGS["separation"]).template
    state = PriorControlState(
        mode="music",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        music_mode="separation",
        music_model="H617A",
        music_body=body,
        music_sensitivity=50,
        music_color=(4, 5, 6),
        music_separation_point=4,
        music_separation_gradient=False,
    )
    with (
        patch.object(coord, "send_command", new=AsyncMock()) as send,
        patch.object(coord, "async_write_music_sequence", new=AsyncMock()) as sequence,
        patch.object(coord, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coord.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is False  # accepted bytes are not full-settings readback
    sequence.assert_awaited_once_with(
        prepare_music_body_writes("H617A", "separation", 50, body, profile=coord.profile),
        mode_code=MUSIC_MODE_SLUGS["separation"],
        physical_ic_count=coord.profile.physical_ic_count,
        intent=ControlIntent.APPLY,
    )
    send.assert_awaited_once()
    assert send.await_args.args == (build_brightness(72, "H617A"),)
    send.await_args.kwargs["write_guard"]()
    refresh.assert_awaited_once_with(
        RefreshRequest(on=True, brightness=72, music_mode="separation", music_sensitivity=50)
    )


async def test_restore_effect_control_state_reapplies_complete_video_profile(h6199):
    from tests.test_h6199_capabilities import set_qualified_identity

    set_qualified_identity(h6199)
    initial = h6199.capture_effect_control_state()
    state = PriorControlState(
        mode="video",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        video_mode="game",
        video_full_screen=False,
        video_saturation=63,
        video_sound_effects=True,
        video_sound_effects_softness=27,
        white_balance_red=21,
        white_balance_blue=5,
        white_balance_flag=1,
        relative_brightness_left=20,
        relative_brightness_top=30,
        relative_brightness_right=40,
        relative_brightness_bottom=50,
        blank_screen=True,
        blank_screen_detection=2,
        blank_screen_low_brightness_duration_seconds=10,
        blank_screen_same_tone_duration_seconds=120,
    )

    with (
        patch(f"{M}_recovery.apply_white_balance", new_callable=AsyncMock, return_value=True) as white_balance,
        patch(
            f"{M}_recovery.apply_relative_brightness", new_callable=AsyncMock, return_value=True
        ) as relative_brightness,
        patch(f"{M}_recovery.apply_blank_screen", new_callable=AsyncMock, return_value=True) as blank_screen,
        patch(f"{M}_recovery.apply_active_video_mode", new_callable=AsyncMock, return_value=True) as video_mode,
        patch.object(h6199, "send_command", new=AsyncMock()),
        patch.object(h6199, "refresh_state", new=AsyncMock(return_value=True)),
    ):
        recovered = await h6199.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is True
    white_balance.assert_awaited_once_with(h6199, (21, 5), flag=1)
    relative_brightness.assert_awaited_once_with(h6199, (20, 30, 40, 50))
    blank_screen.assert_awaited_once_with(h6199, True)
    video_mode.assert_awaited_once_with(
        h6199,
        parameters=None,
        mode="game",
        requested_values={"full_screen": False, "saturation": 63, "sound_effects": True, "sound_effects_softness": 27},
    )
    assert h6199.capture_effect_control_state() == initial


@pytest.mark.parametrize(
    ("enabled", "policy", "change_during_restore"),
    [
        pytest.param(False, (1, 30, 240), False, id="restore-enable-with-live-policy"),
        pytest.param(True, (1, 30, 240), False, id="policy-only-no-blank-write"),
        pytest.param(False, (None, 30, 240), False, id="unknown-detection"),
        pytest.param(False, (1, None, 240), False, id="unknown-low-duration"),
        pytest.param(False, (1, 30, None), False, id="unknown-same-duration"),
        pytest.param(False, (1, 30, 240), True, id="policy-changes-at-physical-boundary"),
    ],
)
async def test_blank_screen_recovery_preserves_live_policy(h6199, enabled, policy, change_during_restore):
    from tests.test_h6199_capabilities import QUALIFIED

    vars(h6199).update(QUALIFIED)
    h6199._confirmed_identity_fields.update(video_identity_fields(h6199.profile))
    h6199.is_on = True
    h6199.color_mode = ParsedMode.SCENE
    h6199.effect = "candlelight"
    h6199._scene_code = MODEL_SCENES["H6199"]["candlelight"].code
    h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 1, 2, 10, 0, 120, 0])))
    state = h6199.capture_effect_control_state()
    h6199.blank_screen = enabled
    (
        h6199.blank_screen_detection,
        h6199.blank_screen_low_brightness_duration_seconds,
        h6199.blank_screen_same_tone_duration_seconds,
    ) = policy
    client = _c(write_gatt_char=AsyncMock())

    async def connect():
        if not client.write_gatt_char.await_count:
            assert h6199.blank_screen is enabled
            assert "blank_screen" not in h6199._expected_state
        if change_during_restore:
            h6199._notify_callback(None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, 0, 0, 60, 0, 44, 1])))
        return client

    async def refresh_policy(request=DEFAULT_REFRESH_REQUEST):
        if request.display_settings and None not in policy:
            h6199._notify_callback(
                None, bytearray(_packet(0xAA, 0xA9, [0x0A, 0x06, int(enabled), policy[0], policy[1], 0, policy[2], 0]))
            )
        return True

    with (
        patch.object(h6199, "_ensure_connected", new=AsyncMock(side_effect=connect)),
        patch.object(h6199, "refresh_state", new=AsyncMock(side_effect=refresh_policy)) as refresh,
    ):
        if None in policy or change_during_restore:
            message = "policy changed before write" if change_during_restore else "policy state has not been read"
            with pytest.raises(ValueError, match=message):
                await h6199.async_restore_effect_control_state(state, overwritten_diy_code=None)
            client.write_gatt_char.assert_not_awaited()
            refresh.assert_awaited_once_with(RefreshRequest(display_settings=frozenset({"blank_screen"})))
            assert h6199.blank_screen is enabled
            assert "blank_screen" not in h6199._expected_state
        else:
            recovered = await h6199.async_restore_effect_control_state(state, overwritten_diy_code=None)
            scene = MODEL_SCENES["H6199"]["candlelight"]
            assert recovered is (not bool(scene.param))
            packets = ([] if enabled else [build_blank_screen(True, "H6199", *policy)]) + [
                build_power(True, "H6199"),
                build_brightness(state.brightness_pct, "H6199"),
                build_scene_activation("H6199", scene.code, scene.music_code),
            ]
            assert client.write_gatt_char.await_args_list == [
                call(WRITE_UUID, packet, response=False) for packet in packets
            ]
            assert refresh.await_args_list == (
                []
                if enabled
                else [
                    call(RefreshRequest(display_settings=frozenset({"blank_screen"}))),
                    call(RefreshRequest(blank_screen=True)),
                ]
            ) + [call(RefreshRequest(on=True, brightness=state.brightness_pct, scene_code=scene.code))]
            assert h6199.blank_screen is True
    assert (
        h6199.blank_screen_detection,
        h6199.blank_screen_low_brightness_duration_seconds,
        h6199.blank_screen_same_tone_duration_seconds,
    ) == ((0, 60, 300) if change_during_restore else policy)


async def test_restore_effect_control_state_reapplies_h6199_scene(h6199):
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="forest",
    )
    scene = MODEL_SCENES["H6199"]["forest"]

    with (
        patch.object(h6199, "send_command", new_callable=AsyncMock) as send,
        patch.object(h6199, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await h6199.async_restore_effect_control_state(
            state,
            overwritten_diy_code=None,
        )

    assert recovered is (not bool(scene.param))
    assert send.await_args_list == [
        call(build_power(True, "H6199")),
        call(build_brightness(72, "H6199")),
        call(build_scene_activation("H6199", scene.code, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=72, scene_code=scene.code))


async def test_restore_h6179_scene_converts_legacy_catalogue_code_to_wire_selector(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:78",
        "H6179",
        configuration_url=_CONFIGURATION_URL,
    )
    scene = MODEL_SCENES["H6179"]["karst cave"]
    selector = scene_selector_code("H6179", scene)
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="karst cave",
        scene_code=scene.code,
    )

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        recovered = await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)

    assert recovered is False
    assert send.await_args_list == [
        call(build_power(True, "H6179")),
        call(build_brightness(72, "H6179")),
        call(build_scene_activation("H6179", selector, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=72, scene_code=selector))


async def test_h6179_zero_kelvin_rgb_observation_replaces_retained_white_and_restores_rgb(hass):
    coordinator = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 1, [1])))
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0D, 255, 255, 255, 0x0E, 0x10, 255, 203, 141])))
    assert coordinator.color_temp_kelvin == 3600
    rgb = table_kelvin_rgb(3600)
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 5, [0x0D, *rgb, 0, 0, 0, 0, 0])))
    state = PriorControlState.from_dict(coordinator.capture_effect_control_state().to_dict())
    assert state.color_temp_kelvin is None and state.rgb_color == rgb

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None)

    assert [entry.args[0] for entry in send.await_args_list] == [
        build_power(True, "H6179"),
        build_brightness(100, "H6179"),
        build_color_rgb(*rgb, "H6179"),
    ]
    refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=100, rgb_color=rgb, zero_kelvin=True))


async def test_h6179_off_grid_persisted_kelvin_restores_against_normalised_readback(hass, monkeypatch, virtual_clock):
    coord = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    client = _c(write_gatt_char=AsyncMock())
    coord._client = client
    monkeypatch.setattr(coord, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)

    async def respond(_uuid, packet, **kwargs):
        replies = {
            b"\xaa\x01": _packet(0xAA, 1, [1]),
            b"\xaa\x04": _packet(0xAA, 4, [254]),
            b"\xaa\x05": _packet(0xAA, 5, [0x0D, 255, 255, 255, 7, 0xD0, 255, 141, 11]),
        }
        if reply := replies.get(packet[:2]):
            coord._notify_callback(None, bytearray(reply))

    client.write_gatt_char.side_effect = respond
    state = PriorControlState.from_dict(
        PriorControlState(
            mode="colour", is_on=True, brightness_pct=100, rgb_color=(255, 141, 11), color_temp_kelvin=2001
        ).to_dict()
    )
    assert await coord.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert coord.color_temp_kelvin == 2000


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize(
    "outcome",
    ["match", "mismatch", "missing", "write_failure", "reconnect_failure", "profile_changed", "subscription_changed"],
)
async def test_h6179_current_adaptation_reconnects_without_replay_and_requires_fresh_readback(
    hass, monkeypatch, virtual_clock, enabled, outcome
):
    from bleak.exc import BleakError

    coord = GoveeBLECoordinator(hass, "55:66:77:88:99:AA", "H6179", configuration_url=_CONFIGURATION_URL)
    coord.pact_type, coord.pact_code = 1, 1
    coord._resolve_device_profile()
    coord.boolean_control_state["limit"] = enabled
    old = _c(write_gatt_char=AsyncMock())
    new = _c(write_gatt_char=AsyncMock())
    coord._client = old
    connections = 0

    async def connect():
        nonlocal connections
        connections += 1
        if connections > 2 and outcome == "reconnect_failure":
            raise BleakError("Restarted controller is unavailable")
        coord._client = old if connections <= 2 else new
        if connections > 2 and outcome == "profile_changed":
            coord.pact_type, coord.pact_code = 10, 1
            coord._resolve_device_profile()
        return coord._client

    async def respond(_uuid, packet, **kwargs):
        if packet[:2] == b"\xaa\x0e" and outcome in {"match", "mismatch", "subscription_changed"}:
            coord._notify_callback(
                None, bytearray(_packet(0xAA, 0x0E, [int(not enabled if outcome == "mismatch" else enabled)]))
            )
            if outcome == "subscription_changed":
                coord._notification_token = object()

    new.write_gatt_char.side_effect = respond

    async def write_setting(_uuid, packet, **kwargs):
        if outcome == "write_failure":
            raise BleakError("Controller disconnected during setting write")
        coord._notify_callback(None, bytearray(_packet(0xAA, 0x0E, [int(enabled)])))

    old.write_gatt_char.side_effect = write_setting
    monkeypatch.setattr(coord, "_ensure_connected", connect)
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    if outcome == "match":
        await coord.async_set_boolean_control("limit", enabled)
        assert coord.boolean_control_state["limit"] is enabled
    else:
        with pytest.raises((ValueError, BleakError)):
            await coord.async_set_boolean_control("limit", enabled)
    old.disconnect.assert_awaited_once()
    assert [item.args[1] for item in old.write_gatt_char.await_args_list] == [_packet(0x33, 0x0E, [int(enabled)])]
    assert all(item.args[1][:1] == b"\xaa" for item in new.write_gatt_char.await_args_list)
    coord._clear_client_state(coord._client)


async def test_restore_effect_control_state_maps_h617e_legacy_scene_name(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:78",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="aurora",
    )
    scene = MODEL_SCENES["H617E"]["aurora-a"]

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(scene.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(72, "H617E")),
        call(build_scene_activation("H617E", scene.code, scene.music_code)),
    ]
    refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=72, scene_code=scene.code))


async def test_restore_effect_control_state_preserves_h617e_raw_legacy_scene(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:79",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    exact_codes = {scene.code for scene in MODEL_SCENES["H617E"].values()}
    legacy_name, legacy = next(
        (name, scene) for name, scene in MODEL_SCENES["H617A"].items() if scene.code not in exact_codes
    )
    coordinator.is_on = True
    coordinator.color_mode = ParsedMode.SCENE
    coordinator._scene_code = legacy.code
    coordinator.effect = None
    state = coordinator.capture_effect_control_state()

    assert state.mode == "scene"
    assert state.scene_code == legacy.code
    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True) as refresh,
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(legacy.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(state.brightness_pct, "H617E")),
        call(build_scene_activation("H617E", legacy.code, legacy.music_code)),
    ]
    refresh.assert_awaited_once_with(RefreshRequest(on=True, brightness=state.brightness_pct, scene_code=legacy.code))


async def test_restore_effect_control_state_uses_legacy_identity_to_disambiguate_scene_code(hass):
    coordinator = GoveeBLECoordinator(
        hass,
        "22:33:44:55:66:80",
        "H617E",
        configuration_url=_CONFIGURATION_URL,
    )
    legacy = MODEL_SCENES["H617A"]["aurora"]
    state = PriorControlState(
        mode="scene",
        is_on=True,
        brightness_pct=72,
        rgb_color=(1, 2, 3),
        effect="aurora",
        scene_code=legacy.code,
    )

    with (
        patch.object(coordinator, "send_command", new_callable=AsyncMock) as send,
        patch.object(coordinator, "refresh_state", new_callable=AsyncMock, return_value=True),
    ):
        assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is (
            not bool(legacy.param)
        )

    assert send.await_args_list == [
        call(build_power(True, "H617E")),
        call(build_brightness(72, "H617E")),
        call(build_scene_activation("H617E", legacy.code, legacy.music_code)),
    ]
