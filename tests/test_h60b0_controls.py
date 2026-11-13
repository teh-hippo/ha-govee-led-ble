import asyncio
import time
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from custom_components.ha_govee_led_ble.const import ReadDomain, device_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_refresh import RefreshRequest
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES
from custom_components.ha_govee_led_ble.effect_compiler import compile_effect, validate_compiled_geometry
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.effect_runtime import async_prepare_effect_control_state
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_boolean_control,
    build_boolean_control_query,
    build_brightness,
    build_colour_mode_query,
    build_hardware_query,
    build_pact_query,
    build_power_on_behaviour,
    build_segment_query,
    build_source_value,
    parse_a3_effect_envelope,
    parse_command_ack_result,
    require_profile_packet,
    table_kelvin_rgb,
    upload_ack_mode,
    upload_ack_subtype,
    upload_ack_success,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_brightness_packets,
    build_segment_color,
    build_segment_color_temp,
    build_segment_paint,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.light_source import GoveeBLESourceLight
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.protocol_core import serialize_native_body
from custom_components.ha_govee_led_ble.transport import reassemble_a3, xor_checksum

PROFILE = device_profile("H60B0", 1, 2)


def frame(prefix: str) -> bytes:
    content = bytes.fromhex(prefix).ljust(19, b"\x00")
    return content + bytes((xor_checksum(content),))


@pytest.mark.parametrize("pact_code", [1, 2, 3])
@pytest.mark.parametrize("colour", [{"rgb_color": (1, 2, 3)}, {"color_temp_kelvin": 5000}])
async def test_main_colour_is_rejected_without_changing_sources(mock_coordinator, pact_code, colour):
    coordinator = mock_coordinator
    coordinator.model, coordinator.profile = "H60B0", device_profile("H60B0", 1, pact_code)
    coordinator.source_static_intents = {"top": 2700, "side": (0, 0, 255)}
    coordinator._expected_state = {}
    before_segments = list(coordinator.segment_colors)
    before_expectations = dict(coordinator._expected_state)
    light = GoveeBLELight(coordinator)
    assert light.supported_color_modes == {ColorMode.BRIGHTNESS}
    for key in ("top", "side"):
        assert GoveeBLESourceLight(coordinator, key).supported_color_modes == {ColorMode.RGB, ColorMode.COLOR_TEMP}
    assert GoveeBLESourceLight(coordinator, "bottom").supported_color_modes == {ColorMode.COLOR_TEMP}
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(brightness=128, **colour)
    assert error.value.translation_key == "area_colour_only"
    coordinator.send_command.assert_not_awaited()
    assert coordinator.source_static_intents == {"top": 2700, "side": (0, 0, 255)}
    assert coordinator.segment_colors == before_segments
    assert coordinator._expected_state == before_expectations


async def test_main_ha_service_uses_only_advertised_brightness(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile, coordinator.is_on = PROFILE, True
    coordinator._client = MagicMock(is_connected=True)
    coordinator.send_command = AsyncMock()
    coordinator.refresh_state = AsyncMock(return_value=True)
    coordinator.source_static_intents = {"top": 2700, "side": (0, 0, 255)}
    light = GoveeBLELight(coordinator)
    light._attr_device_info = None
    light.async_added_to_hass = AsyncMock()
    assert await async_setup_component(hass, "light", {})
    await hass.data["light"].async_add_entities([light])
    await hass.services.async_call(
        "light", "turn_on", {"entity_id": light.entity_id, "brightness": 128, "rgb_color": [1, 2, 3]}, blocking=True
    )
    assert [call.args[0] for call in coordinator.send_command.await_args_list] == [build_brightness(50)]
    state = hass.states.get(light.entity_id)
    assert state.attributes["supported_color_modes"] == ["brightness"]
    assert "rgb_color" not in state.attributes and "color_temp_kelvin" not in state.attributes
    assert coordinator.source_static_intents == {"top": 2700, "side": (0, 0, 255)}


@pytest.fixture
def native_sources(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._refresh_h607c_advertisements = lambda: None
    client = MagicMock(is_connected=True, disconnect=AsyncMock())
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic() - 1
    coordinator._ensure_connected = AsyncMock(return_value=client)
    coordinator._async_supersede_effect_preview = AsyncMock()
    physical = {}

    def observe(flags=0xE0):
        physical.update(
            {
                control: bool(flags & mask)
                for control, mask in (("top_enabled", 0x40), ("side_enabled", 0x20), ("bottom_enabled", 0x10))
            }
        )
        coordinator._notify_callback(None, bytearray(frame(f"aa42{flags:02x}0a8c320a8c64")))

    async def write(_client, packet, **kwargs):
        if guard := kwargs.get("before_write"):
            guard()
        if packet[:2] == bytes.fromhex("aa42"):
            flags = 0x80 | sum(
                mask
                for control, mask in (("top_enabled", 0x40), ("side_enabled", 0x20), ("bottom_enabled", 0x10))
                if physical.get(control)
            )
            observe(flags)

    async def send(packet, **kwargs):
        if guard := kwargs.get("write_guard"):
            guard()
        coordinator.control_write_attempts += 1
        if on_write := kwargs.get("on_write"):
            on_write()
        control = {1: "top_enabled", 2: "side_enabled", 3: "bottom_enabled"}[packet[2]]
        enabled = bool(packet[3])
        physical[control] = enabled
        if enabled:
            for group in coordinator.profile.exclusive_source_groups:
                if control in group:
                    physical.update({name: False for name in group if name != control})
        await asyncio.sleep(0)

    coordinator._async_write_packet = AsyncMock(side_effect=write)
    coordinator.send_command = AsyncMock(side_effect=send)
    observe()
    return coordinator, observe


async def test_native_source_power_requires_current_pact_confirmation(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)
    coordinator._confirmed_identity_fields.discard("pact")
    with pytest.raises(HomeAssistantError) as error:
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert error.value.translation_key == "identity_not_ready"
    coordinator.send_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("flags", "control", "enabled", "key"),
    [
        (0xE0, "bottom_enabled", True, "source_limit"),
        (0xA0, "side_enabled", False, "last_source"),
    ],
)
async def test_native_source_constraints_reject_before_write(native_sources, flags, control, enabled, key):
    coordinator, observe = native_sources
    observe(flags)
    before = dict(coordinator.boolean_control_state)
    with pytest.raises(HomeAssistantError) as error:
        await coordinator.async_set_source_enabled(control.removesuffix("_enabled"), enabled)
    assert error.value.translation_key == key
    coordinator.send_command.assert_not_awaited()
    assert coordinator.boolean_control_state == before


async def test_concurrent_source_enables_cannot_exceed_native_limit(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)
    results = await asyncio.gather(
        coordinator.async_set_boolean_control("top_enabled", True),
        coordinator.async_set_boolean_control("bottom_enabled", True),
        return_exceptions=True,
    )
    assert sum(isinstance(result, HomeAssistantError) for result in results) == 1
    assert sum(coordinator.boolean_control_state.values()) == 2
    assert coordinator.send_command.await_count == 1


async def test_original_revision_swaps_top_and_bottom_without_disabling_side(native_sources):
    coordinator, observe = native_sources
    coordinator.profile = device_profile("H60B0", 1, 1)
    observe(0xB0)
    await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": True, "bottom_enabled": False}
    assert [call.args[0] for call in coordinator.send_command.await_args_list] == [frame("33300101")]


async def test_source_selection_change_before_physical_write_is_rejected(native_sources):
    coordinator, observe = native_sources
    observe(0xA0)

    async def change_before_write(_packet, **kwargs):
        observe(0xB0)
        kwargs["write_guard"]()

    coordinator.send_command.side_effect = change_before_write
    with pytest.raises(ValueError, match="selection changed"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator.control_write_attempts == 0
    assert coordinator.boolean_control_state == {"top_enabled": False, "side_enabled": True, "bottom_enabled": True}


@pytest.fixture
def source_wire(native_sources):
    coordinator, _observe = native_sources
    client = coordinator._client
    coordinator._async_write_packet = GoveeBLECoordinator._async_write_packet.__get__(coordinator)
    coordinator.send_command = GoveeBLECoordinator.send_command.__get__(coordinator)
    coordinator.async_prepare_identity_gated_control = AsyncMock(return_value=lambda: None)
    coordinator._authorization_profile = MagicMock(return_value=PROFILE)
    state = {
        "apply": False,
        "flags": 0xE0,
        "top": 2700,
        "colours": [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)],
        "levels": [40] * 8 + [60],
        "ripple": 50,
        "bottom_brightness": 40,
        "drop_source_readback": False,
    }

    async def write(_uuid, packet, **_kwargs):
        command = packet[1]
        if packet[0] == 0x33 and state["apply"]:
            if command == 0x01:
                state["flags"] = state["flags"] | 0x80 if packet[2] else state["flags"] & ~0x80
            elif command == 0x30:
                mask = {1: 0x40, 2: 0x20, 3: 0x10}[packet[2]]
                state["flags"] = state["flags"] | mask if packet[3] else state["flags"] & ~mask
            elif command == 0x05 and packet[2:5] == bytes.fromhex("2c0103"):
                state["ripple"] = packet[5]
            elif command == 0x05 and packet[2:5] == bytes.fromhex("2c0302"):
                state["bottom_brightness"] = packet[5]
            static = parse_static_write(packet, "H60B0", profile=PROFILE)
            if static is not None:
                assert packet[2] != 0x0D
                for index in range(9):
                    if static.segment_mask & (1 << index):
                        if static.rgb is not None or static.kelvin is not None:
                            state["colours"][index] = static.rgb or table_kelvin_rgb(static.kelvin)
                        if static.brightness_pct is not None:
                            state["levels"][index] = static.brightness_pct
                if static.segment_mask & 0x100 and (static.rgb is not None or static.kelvin is not None):
                    state["top"] = static.kelvin or 0
        if command in (0x05, 0x42):
            if command == 0x42 and state["drop_source_readback"]:
                return
            prefix = "aa052c" if command == 0x05 else f"aa42{state['flags']:02x}"
            response = frame(prefix + f"{state['top']:04x}{state['ripple']:02x}0fa0{state['bottom_brightness']:02x}")
        elif command == 0xA5:
            group = packet[2]
            offset = (group - 1) * 4
            body = "".join(
                f"{state['levels'][index]:02x}" + bytes(state["colours"][index]).hex()
                for index in range(offset, min(offset + 4, 9))
            )
            response = frame(f"aaa5{group:02x}" + body)
        elif command == 0x01:
            response = frame("aa0101")
        elif command == 0x04:
            response = frame("aa0432")
        else:
            return
        coordinator._notify_callback(None, bytearray(response))

    client.write_gatt_char = AsyncMock(side_effect=write)
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.source_static_intents = {"top": 2700, "side": (0, 0, 255)}
    return coordinator, state


@pytest.mark.parametrize("reconnect_flags", [None, 0xB0])
async def test_source_retry_rejects_missing_or_changed_selection(source_wire, native_sources, reconnect_flags):
    coordinator, state = source_wire
    _, observe = native_sources
    client = coordinator._client
    state["flags"] = 0xA0
    observe(0xA0)

    async def connect():
        if coordinator._client is None:
            coordinator._client = client
            coordinator._notification_token = object()
            coordinator._notify_started_monotonic = time.monotonic()
            if reconnect_flags is not None:
                observe(reconnect_flags)
        return client

    coordinator._ensure_connected = AsyncMock(side_effect=connect)
    client.write_gatt_char.side_effect = BleakError("Physical write failed")
    with pytest.raises(ValueError, match="selection changed"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert [call.args[1] for call in client.write_gatt_char.await_args_list] == [frame("33300101")]
    assert coordinator.boolean_control_state == (
        {} if reconnect_flags is None else {"top_enabled": False, "side_enabled": True, "bottom_enabled": True}
    )


@pytest.mark.parametrize("operation", ["kelvin", "rgb"])
async def test_unconfirmed_source_write_reconciles_real_area_state(source_wire, virtual_clock, operation):
    coordinator, _state = source_wire
    if operation == "kelvin":
        request = coordinator.async_set_segment_kelvin(
            build_segment_color_temp([9], 5000, "H60B0", profile=PROFILE), requested_kelvin=5000
        )
    else:
        request = coordinator.async_paint_segments([(list(range(1, 9)), (255, 0, 0))])
    with pytest.raises((TimeoutError, RuntimeError)):
        await request
    top, side = GoveeBLESourceLight(coordinator, "top"), GoveeBLESourceLight(coordinator, "side")
    assert top.color_temp_kelvin == 2700
    assert side.color_mode is ColorMode.RGB
    assert side.rgb_color == (0, 0, 255)
    assert "source_kelvin_top" not in coordinator._expected_state
    assert "source_kelvin_side" not in coordinator._expected_state
    assert coordinator.segment_state_source == "observed"
    assert GoveeBLELight(coordinator).color_mode is ColorMode.BRIGHTNESS
    assert GoveeBLELight(coordinator).brightness is not None


async def test_cancelled_source_kelvin_write_does_not_query_recovery(source_wire):
    coordinator, _state = source_wire
    client = coordinator._client
    write = client.write_gatt_char.side_effect
    packet = build_segment_color_temp([9], 5000, "H60B0", profile=PROFILE)

    async def cancel_kelvin(uuid, command, **kwargs):
        if command == packet:
            raise asyncio.CancelledError
        await write(uuid, command, **kwargs)

    client.write_gatt_char.side_effect = cancel_kelvin
    with pytest.raises(asyncio.CancelledError):
        await coordinator.async_set_segment_kelvin(packet, requested_kelvin=5000)
    assert client.write_gatt_char.await_args_list[-1].args[1] == packet
    assert not coordinator._control_arbiter.locked()
    assert not coordinator._lock.locked()


@pytest.mark.parametrize("native_setting", [None, ("top", "ripple_speed", 60), ("bottom", "brightness", 50)])
async def test_effect_stop_restores_mixed_source_capture_without_aggregate_colour(
    source_wire, virtual_clock, native_setting
):
    coordinator, state = source_wire
    state["apply"] = True
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    if native_setting is not None:
        await coordinator.async_set_source_value(*native_setting)
        assert coordinator.segment_state_source == "observed"
    before = coordinator.capture_effect_control_state()
    assert before.top_kelvin == 2700
    assert before.source_static_intents == {"top": 2700, "side": (0, 0, 255)}
    assert before.restorable_source_colour(PROFILE)
    assert PriorControlState.from_dict(before.to_dict()) == before
    await coordinator.send_command(frame("3305040100"))
    assert coordinator._pre_mode_snapshot.source_state == before
    state["apply"] = True
    state["top"] = 0
    state["colours"] = [(255, 0, 0)] * 9
    coordinator.source_static_intents.clear()
    coordinator.color_mode = ParsedMode.SCENE
    await GoveeBLELight(coordinator)._async_clear_effect()
    assert state["colours"] == [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)]
    assert coordinator.capture_effect_control_state().source_static_intents == before.source_static_intents
    assert coordinator._client.write_gatt_char.await_count > 0


async def test_music_captures_sources_before_its_mode_guard_runs(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"] = True
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    before = coordinator.capture_effect_control_state()

    async def activate(packets, **kwargs):
        for index in range(len(packets)):
            kwargs["packet_write_guard"](index)

    coordinator.async_write_effect_sequence = AsyncMock(side_effect=activate)
    await coordinator.async_select_music_slug("spectrum")
    assert coordinator._pre_mode_snapshot.source_state == before
    assert coordinator.color_mode is ParsedMode.MUSIC
    state["top"], state["colours"] = 0, [(255, 0, 0)] * 9
    await GoveeBLELight(coordinator)._async_clear_effect()
    assert state["colours"] == [(0, 0, 255)] * 8 + [table_kelvin_rgb(2700)]


async def test_missing_switch_readback_requires_fresh_flags_before_next_enable(source_wire, virtual_clock):
    coordinator, state = source_wire
    client = coordinator._client
    state["apply"], state["flags"], state["drop_source_readback"] = True, 0xA0, True
    coordinator._notify_callback(None, bytearray(frame("aa42a00a8c320fa028")))
    with pytest.raises(ValueError, match="fresh setting readback"):
        await coordinator.async_set_boolean_control("top_enabled", True)
    assert coordinator._fresh_source_power() is None
    with pytest.raises(ValueError, match="complete source power"):
        await coordinator.async_set_boolean_control("bottom_enabled", True)
    source_writes = [call.args[1] for call in client.write_gatt_char.await_args_list if call.args[1][:2] == b"\x33\x30"]
    assert source_writes == [frame("33300101")]
    assert state["flags"] == 0xE0


async def test_reconnected_native_fields_cannot_qualify_cached_segment_layout(source_wire, virtual_clock):
    coordinator, state = source_wire
    assert await coordinator.refresh_state(RefreshRequest(refresh_all=True, query_segments=True))
    assert coordinator.capture_effect_control_state().restorable_source_colour(PROFILE)
    client = coordinator._client
    coordinator._clear_client_state(client)
    await asyncio.sleep(0.1)
    coordinator._client, coordinator._notification_token = client, object()
    coordinator._notify_started_monotonic = asyncio.get_running_loop().time()
    coordinator._notify_callback(None, bytearray(frame("aa052c0a8c320fa028")))
    coordinator._notify_callback(None, bytearray(frame("aa42e00a8c320fa028")))
    state["colours"] = [(255, 0, 0)] * 8 + [table_kelvin_rgb(2700)]
    captured = coordinator.capture_effect_control_state()
    assert captured.segment_colors is None
    assert captured.source_static_intents is None
    with pytest.raises(RuntimeError, match="restor"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)


async def test_source_on_from_master_off_preserves_remembered_siblings(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"], state["flags"] = True, 0x60
    coordinator._notify_callback(None, bytearray(frame("aa42600a8c320fa028")))
    await GoveeBLESourceLight(coordinator, "top").async_turn_on()
    assert coordinator.is_on
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": True, "bottom_enabled": False}
    assert not any(
        call.args[1][:2] == bytes.fromhex("3330") and not call.args[1][3]
        for call in coordinator._client.write_gatt_char.await_args_list
    )


async def test_partial_source_paint_preserves_success_and_untouched_bottom(source_wire, virtual_clock):
    coordinator, state = source_wire
    state["apply"] = True
    write = coordinator._client.write_gatt_char.side_effect
    attempted_masks = []

    async def fail_side(uuid, packet, **kwargs):
        static = parse_static_write(packet, "H60B0", profile=PROFILE) if packet[0] == 0x33 else None
        if static is not None:
            attempted_masks.append(static.segment_mask)
            if static.segment_mask == 0xFF:
                raise RuntimeError("side write failed")
        await write(uuid, packet, **kwargs)

    coordinator._client.write_gatt_char.side_effect = fail_side
    with pytest.raises(RuntimeError, match="side write failed"):
        await coordinator.async_paint_segments([(list(range(1, 10)), (255, 0, 0))])
    assert attempted_masks == [0x100, 0xFF]
    assert GoveeBLESourceLight(coordinator, "top").rgb_color == (255, 0, 0)
    assert GoveeBLESourceLight(coordinator, "side").rgb_color == (0, 0, 255)
    assert coordinator.bottom_kelvin == 4000
    assert coordinator.boolean_control_state["bottom_enabled"] is False


@pytest.mark.parametrize(
    ("packet", "prefix"),
    [
        (build_brightness(50, profile=PROFILE), "330432"),
        (build_color_rgb(1, 2, 3, profile=PROFILE), "33050d0102030000000000"),
        (build_color_temp(4000, profile=PROFILE), "33050dffffff0fa0ffd5a1"),
        (build_segment_color([9], 1, 2, 3, profile=PROFILE), "33052c01010102030000"),
        (build_segment_color([1, 8], 1, 2, 3, profile=PROFILE), "33052c020101020300008100"),
        (build_segment_color_temp([9], 4000, profile=PROFILE), "33052c0101ffd5a10fa0"),
        (build_segment_brightness([9], 40, profile=PROFILE), "33052c010228"),
        (build_segment_brightness([1, 8], 40, profile=PROFILE), "33052c0202288100"),
        (build_source_value("bottom", "brightness", 40, PROFILE), "33052c030228"),
        (build_source_value("bottom", "kelvin", 4000, PROFILE), "33052c03010fa0"),
        (build_source_value("top", "ripple_speed", 30, PROFILE), "33052c01031e"),
        (build_boolean_control("side_enabled", True, "H60B0", profile=PROFILE), "33300201"),
        (build_power_on_behaviour("off", PROFILE), "33410202"),
        (build_boolean_control_query("top_enabled", "H60B0", profile=PROFILE), "aa42"),
        (build_colour_mode_query(profile=PROFILE), "aa05"),
        (build_hardware_query(profile=PROFILE), "aa0703"),
        (build_pact_query(PROFILE), "aaef"),
        (build_segment_query(3, profile=PROFILE), "aaa503"),
    ],
)
def test_source_and_ordinary_commands_match_exact_model_contract(packet, prefix):
    assert packet == frame(prefix)
    require_profile_packet(packet, PROFILE)


def test_mixed_source_writes_partition_without_touching_bottom_or_other_segments():
    colour = build_segment_paint([([1, 9], (1, 2, 3))], "H60B0", profile=PROFILE)
    brightness = build_segment_brightness_packets([1, 9], 40, "H60B0", profile=PROFILE)
    assert colour == [frame("33052c01010102030000"), frame("33052c020101020300000100")]
    assert brightness == [frame("33052c010228"), frame("33052c0202280100")]
    for packets in (colour, brightness):
        assert [parse_static_write(packet, profile=PROFILE).segment_mask for packet in packets] == [256, 1]
        for packet in packets:
            require_profile_packet(packet, PROFILE)


def test_combined_music_ack_tracks_the_outer_mode_and_preserves_envelope_fill():
    packets = prepare_music_request("H60B0", "combined", 50, None, False, {}, profile=PROFILE)
    index = len(packets) - 2
    assert upload_ack_subtype(packets, index, "H60B0", profile=PROFILE) == 0x41
    assert upload_ack_mode(packets, index, "H60B0", profile=PROFILE) == 130
    envelope = reassemble_a3(tuple(packet for packet in packets if packet[0] == 0xA3))
    assert serialize_native_body(parse_a3_effect_envelope(envelope, "H60B0", profile=PROFILE)) == envelope
    for prefix, expected in (("a3418200", True), ("a3418201", False), ("a3413000", None)):
        parsed = parse_command_ack_result(frame(prefix), "H60B0", profile=PROFILE).parsed
        assert parsed is not None
        assert upload_ack_success(parsed, 0x41, 130, protocol=0xA3) is expected


@pytest.mark.parametrize("pact", [(1, 1), (1, 2), (1, 3)])
def test_revision_qualification_does_not_infer_firmware_thresholds(pact):
    profile = device_profile("H60B0", *pact, firmware="1.00.12", hardware="3.05.01")
    assert profile.native_effect_revision == pact[1]
    assert profile.supports_rgb and profile.supports_scenes and profile.supports_ripple_speed
    unknown = device_profile("H60B0", None, None, firmware="1.00.12", hardware="3.05.01")
    with pytest.raises(ValueError):
        require_profile_packet(build_source_value("bottom", "kelvin", 4000, profile), unknown)
    with pytest.raises(ValueError):
        require_profile_packet(build_segment_color([9], 1, 2, 3, profile=profile), unknown)


@pytest.mark.parametrize(
    "prefix",
    [
        "33300401",
        "33300102",
        "33052c0202010001",
        "33052c010365",
        "33052c030265",
        "33052c03010fa1",
        "33052c050101020300000100",
    ],
)
def test_unqualified_sources_masks_and_levels_are_rejected(prefix):
    with pytest.raises(ValueError):
        require_profile_packet(frame(prefix), PROFILE)


async def test_source_readback_is_independent_and_invalid_state_cannot_update_flags(hass, monkeypatch):
    from custom_components.ha_govee_led_ble import coordinator_notifications, h60b0_controls

    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    decode = MagicMock(wraps=h60b0_controls.source_readback)
    monkeypatch.setattr(h60b0_controls, "source_readback", decode)
    monkeypatch.setattr(coordinator_notifications, "source_readback", decode)
    coordinator._notify_callback(None, bytearray(frame("aa42d00bb81e0fa028")))
    decode.assert_called_once()
    assert coordinator.boolean_control_state == {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness, coordinator.ripple_speed) == (4000, 40, 30)
    coordinator._notify_callback(None, bytearray(frame("aa42200bb81e0fa065")))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator.bottom_brightness == 40
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.supported_color_modes == {ColorMode.COLOR_TEMP}
    assert bottom.color_temp_kelvin == 4000 and bottom.brightness == 102
    assert bottom.rgb_color is None


@pytest.mark.parametrize("pact_code", [1, 2, 3])
@pytest.mark.parametrize("prefix", ["aa42b0", "aa052c"])
async def test_reported_source_state_keeps_bottom_values_separate_from_ripple(hass, pact_code, prefix):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = device_profile("H60B0", 1, pact_code)
    coordinator._notify_callback(None, bytearray(frame(prefix + "000032196464")))
    assert (coordinator.top_kelvin, coordinator.ripple_speed) == (0, 50)
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness) == (6500, 100)
    bottom = GoveeBLESourceLight(coordinator, "bottom")
    assert bottom.color_temp_kelvin == 6500
    assert bottom.brightness == 255


async def test_bottom_source_uses_native_attributes_without_segment_writes(mock_coordinator):
    coordinator = mock_coordinator
    coordinator.model, coordinator.profile = "H60B0", PROFILE
    coordinator.is_on = True
    coordinator.boolean_control_state = {"top_enabled": True, "side_enabled": False, "bottom_enabled": True}
    coordinator._async_supersede_effect_preview = AsyncMock()
    coordinator.async_prepare_identity_gated_control = AsyncMock(return_value=lambda: None)
    coordinator.refresh_state = AsyncMock(return_value=True)
    coordinator.async_set_boolean_control = AsyncMock()
    coordinator.async_set_source_value = AsyncMock()
    coordinator.async_set_segment_brightness = AsyncMock()
    coordinator.async_set_segment_kelvin = AsyncMock()
    coordinator._notify_started_monotonic = 1.0
    coordinator._field_revisions["is_on"] = 1
    coordinator._field_received_at.update({"is_on": 2.0, "boolean_bottom_enabled": 2.0})
    coordinator._observed_power_write_generation = coordinator._power_write_generation
    coordinator._observed_power_profile_generation = coordinator._profile_generation
    coordinator._source_power_observation_generation["boolean_bottom_enabled"] = (
        coordinator._power_write_generation,
        coordinator._profile_generation,
    )
    coordinator.async_mask_transaction = MagicMock(
        side_effect=AssertionError("Native source controls do not address segments")
    )
    source = GoveeBLESourceLight(coordinator, "bottom")
    await source.async_turn_on(brightness=102, color_temp_kelvin=4000)
    assert coordinator.async_set_source_value.await_args_list[0].args == ("bottom", "brightness", 40)
    assert coordinator.async_set_source_value.await_args_list[1].args == ("bottom", "kelvin", 4000)
    coordinator.async_set_segment_brightness.assert_not_awaited()
    coordinator.async_set_segment_kelvin.assert_not_awaited()
    coordinator.async_set_boolean_control.assert_not_awaited()


@pytest.mark.parametrize(
    ("source", "attribute", "value", "prefix", "matching_body", "mismatched_body"),
    [
        ("bottom", "brightness", 100, "33052c030264", "000032196464", "000032196432"),
        ("bottom", "kelvin", 6500, "33052c03011964", "000032196464", "0000320fa064"),
        ("top", "ripple_speed", 30, "33052c01031e", "00001e196464", "000032196464"),
    ],
)
@pytest.mark.parametrize("matching", [True, False])
async def test_native_source_setting_requires_fresh_matching_readback(
    hass, source, attribute, value, prefix, matching_body, mismatched_body, matching
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    client = MagicMock(is_connected=True)
    coordinator._client = client
    coordinator._notification_token = object()
    coordinator._ensure_connected = AsyncMock(return_value=client)
    coordinator._async_supersede_effect_preview = AsyncMock()
    body = matching_body if matching else mismatched_body

    async def write(_client, packet, **kwargs):
        if guard := kwargs.get("before_write"):
            guard()
        if callback := kwargs.get("on_write"):
            callback()
        if packet == frame("aa42"):
            coordinator._notify_callback(None, bytearray(frame("aa42f0" + body)))
        if packet == frame("aa05"):
            coordinator._notify_callback(None, bytearray(frame("aa052c" + body)))

    coordinator._async_write_packet = AsyncMock(side_effect=write)
    if matching:
        await coordinator.async_set_source_value(source, attribute, value)
        field = "ripple_speed" if attribute == "ripple_speed" else f"{source}_{attribute}"
        assert getattr(coordinator, field) == value
    else:
        with pytest.raises(ValueError, match="did not confirm"):
            await coordinator.async_set_source_value(source, attribute, value)
    assert [call.args[1] for call in coordinator._async_write_packet.await_args_list] == [
        frame(prefix),
        frame("aa42"),
        *([frame("aa05")] if matching else []),
    ]


async def test_preview_requires_complete_source_values_and_preserves_them_in_storage(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    prior = PriorControlState("scene", True, 50, (1, 2, 3), top_enabled=True, side_enabled=False, bottom_enabled=True)
    coordinator.capture_effect_control_state = MagicMock(return_value=prior)
    with pytest.raises(RuntimeError, match="restorable source values"):
        await async_prepare_effect_control_state(coordinator, require_restorable_static=True)
    complete = replace(prior, top_kelvin=2700, bottom_kelvin=4000, bottom_brightness=40, ripple_speed=30)
    assert PriorControlState.from_dict(complete.to_dict()) == complete
    coordinator.capture_effect_control_state.return_value = complete
    assert await async_prepare_effect_control_state(coordinator, require_restorable_static=True)


async def test_reconnect_revokes_cached_pact_and_qualifies_the_current_marker(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    old_client = MagicMock(is_connected=True)
    coordinator._client = old_client
    coordinator._confirmed_identity_fields.add("pact")
    coordinator._h607c_marker_pact = (1, 2)
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    template = next(
        template
        for template in MODEL_EFFECT_CATALOGUES["H60B0"].templates
        if template.id == "template:h60b0:1:single:1"
    )
    compiled = compile_effect(LibraryItem.new("Older native effect", template.content), "H60B0", profile=PROFILE)
    source_packet = build_source_value("bottom", "brightness", 40, PROFILE)
    coordinator._clear_client_state(old_client)
    assert coordinator.profile.native_effect_revision == 2
    assert not coordinator.identity_fields_confirmed()
    assert coordinator.h607c_pact_readiness == "stale"
    with pytest.raises(ValueError):
        coordinator._validate_authorized_packet(source_packet)
    with pytest.raises(ValueError):
        coordinator._validate_authorized_packet(compiled.upload_packets[0])

    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True, version=0, marker_pact=(1, 3), async_select=AsyncMock(), async_negotiate=AsyncMock()
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert coordinator.profile.native_effect_revision == 3
        assert coordinator.identity_fields_confirmed()
        assert coordinator.h607c_pact_readiness == "ready"
        coordinator._validate_authorized_packet(source_packet)
        with pytest.raises(ValueError, match="revision"):
            validate_compiled_geometry(compiled, coordinator.profile)
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(ValueError):
            coordinator._validate_authorized_packet(source_packet)
        assert coordinator.profile.native_effect_revision == 3
    finally:
        await coordinator.disconnect()


async def test_only_current_subscription_advertisements_can_confirm_pact(hass):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator._client = MagicMock(is_connected=True)
    coordinator._notify_started_monotonic = time.monotonic()
    coordinator._h607c_advertisement_observations = {
        "proxy": (coordinator._notify_started_monotonic - 1, frozenset({(1, 2)}))
    }
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    coordinator._h607c_advertisement_observations["proxy"] = (
        coordinator._notify_started_monotonic + 1,
        frozenset({(1, 2)}),
    )
    coordinator._resolve_h607c_pact()
    assert coordinator.identity_fields_confirmed()
    coordinator._h607c_marker_pact = (1, 3)
    coordinator._resolve_h607c_pact()
    assert not coordinator.identity_fields_confirmed()
    assert not coordinator._authorization_profile().supports_custom_effects


async def test_pact_is_rechecked_after_reply_pacing_before_the_physical_write(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator._client = client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._confirmed_identity_fields.add("pact")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def lose_confirmation():
        coordinator._confirmed_identity_fields.discard("pact")

    monkeypatch.setattr(coordinator._reply_gate, "wait", lose_confirmation)
    with pytest.raises(ValueError):
        await coordinator._async_write_packet(client, packet, arm_expected=True)
    client.write_gatt_char.assert_not_awaited()


@pytest.fixture
def pact_connection(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.pact_type, coordinator.pact_code = 1, 2
    coordinator.profile = PROFILE
    coordinator._h607c_advertisement_observations = {"cached": (time.monotonic() - 10, frozenset({(1, 2)}))}
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    coordinator._encryption = MagicMock(
        ready=True,
        version=0,
        marker_pact=None,
        async_select=AsyncMock(),
        async_negotiate=AsyncMock(),
        encode=lambda packet: packet,
        decode=lambda packet: packet,
    )
    monkeypatch.setattr(
        "custom_components.ha_govee_led_ble.coordinator.async_establish_ble_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    return coordinator, client


@pytest.mark.parametrize(("revision", "cached"), [(1, True), (2, True), (3, True), (9, True), (2, False)])
async def test_live_pact_read_qualifies_without_marker_or_connected_advertisements(pact_connection, revision, cached):
    coordinator, client = pact_connection
    if not cached:
        coordinator.pact_type = coordinator.pact_code = None
        coordinator.profile = device_profile("H60B0", None, None)
        coordinator._h607c_advertisement_observations.clear()
    initial_profile = coordinator.profile
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)

    async def write(_uuid, query, **kwargs):
        assert query == frame("aaef")
        assert source.available is cached
        assert coordinator.profile == initial_profile
        assert not coordinator.identity_fields_confirmed()
        with pytest.raises(ValueError):
            coordinator._require_writable_packet(
                packet,
                require_profile_packet,
                arm_expected=True,
                static=parse_static_write(packet, coordinator.model, profile=coordinator.profile),
            )
        receive = client.start_notify.await_args.args[1]
        receive(None, bytearray(frame(f"aaef0001{revision:02x}" + "55" * 14)))

    client.write_gatt_char.side_effect = write
    try:
        assert await coordinator._ensure_connected() is client
        client.write_gatt_char.assert_awaited_once()
        assert coordinator.identity_fields_confirmed()
        assert coordinator._authorization_profile().supports_rgb is (revision != 9)
        if revision != 9:
            assert source.available
            assert coordinator.profile.native_effect_revision == revision
            coordinator._validate_authorized_packet(packet)
        else:
            assert not source.available
            assert coordinator._pact_query_result == "unsupported"
            with pytest.raises(ValueError):
                await coordinator._async_write_packet(client, packet, arm_expected=True)
            client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


async def test_pact_timeout_preserves_presentation_but_not_write_authority(pact_connection, virtual_clock):
    coordinator, client = pact_connection
    source = GoveeBLESourceLight(coordinator, "top")
    packet = build_source_value("bottom", "brightness", 40, PROFILE)
    try:
        assert await coordinator._ensure_connected() is client
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE and source.available
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        coordinator._validate_authorized_packet(build_brightness(50, profile=PROFILE))
        with pytest.raises(ValueError):
            coordinator._validate_authorized_packet(packet)
        receive = client.start_notify.await_args.args[1]
        malformed = bytearray(frame("aaef000102"))
        malformed[-1] ^= 1
        receive(None, malformed)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000102")))
        assert coordinator.identity_fields_confirmed()
        coordinator._clear_client_state(client)
        assert not coordinator.identity_fields_confirmed()
        receive(None, bytearray(frame("aaef000103")))
        assert not coordinator._connection_pacts
        client.write_gatt_char.side_effect = lambda *args, **kwargs: receive(None, bytearray(frame("aaef000103")))
        assert await coordinator._ensure_connected() is client
        assert not coordinator.identity_fields_confirmed()
        assert coordinator._pact_query_result == "timeout"
        assert coordinator.profile == PROFILE
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize("conflict", ["query", "marker", "advertisement"])
async def test_live_pact_conflicts_revoke_write_authority(pact_connection, conflict):
    coordinator, client = pact_connection
    client.write_gatt_char.side_effect = lambda *args, **kwargs: client.start_notify.await_args.args[1](
        None, bytearray(frame("aaef000102"))
    )
    try:
        await coordinator._ensure_connected()
        assert coordinator.identity_fields_confirmed()
        if conflict == "query":
            client.start_notify.await_args.args[1](None, bytearray(frame("aaef000103")))
        elif conflict == "marker":
            coordinator._h607c_marker_pact = (1, 3)
            coordinator._resolve_h607c_pact()
        else:
            coordinator._h607c_advertisement_observations["current"] = (time.monotonic(), frozenset({(1, 3)}))
            coordinator._resolve_h607c_pact()
        assert coordinator.h607c_pact_readiness == "conflicting"
        assert not coordinator.identity_fields_confirmed()
        assert not coordinator._authorization_profile().supports_rgb
        with pytest.raises(ValueError):
            await coordinator._async_write_packet(
                client, build_source_value("bottom", "brightness", 40, PROFILE), arm_expected=True
            )
        client.write_gatt_char.assert_awaited_once()
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0x30, (False, False, True, True)), (0xB0, (True, False, True, True)), (0xA0, (True, False, True, False))],
)
async def test_reported_source_notifications_update_only_power_fields(hass, flags, expected):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H60B0", configuration_url=None)
    coordinator.profile = PROFILE
    coordinator._notify_callback(None, bytearray(frame("aa42d00bb81e0fa028")))
    native_revisions = {field: coordinator._field_revisions[field] for field in ("bottom_kelvin", "ripple_speed")}
    notification = frame(f"ee3001{flags:02x}" + "ab" * 15)
    coordinator._notify_callback(None, bytearray(notification))
    controls = ("top_enabled", "side_enabled", "bottom_enabled")
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    assert (coordinator.bottom_kelvin, coordinator.bottom_brightness, coordinator.ripple_speed) == (4000, 40, 30)
    assert {field: coordinator._field_revisions[field] for field in native_revisions} == native_revisions
    assert not coordinator.identity_fields_confirmed()
    assert ReadDomain.PACT not in coordinator._domain_revisions
    broken = bytearray(notification)
    broken[3] ^= 0xF0
    coordinator._notify_callback(None, broken)
    assert (coordinator.is_on, *(coordinator.boolean_control_state[name] for name in controls)) == expected
    coordinator._expected_state["boolean_top_enabled"] = (True, time.monotonic() + 10)
    coordinator.boolean_control_state["top_enabled"] = True
    previous = coordinator._field_revisions["boolean_top_enabled"]
    coordinator._notify_callback(None, bytearray(notification))
    assert coordinator.boolean_control_state["top_enabled"] is True
    assert coordinator._field_revisions["boolean_top_enabled"] == previous
