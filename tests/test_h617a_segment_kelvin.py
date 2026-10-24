"""Masked Kelvin service: real writer, direct-device replay, and failure boundaries."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_colour_temperature
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_segment_color_temp,
    parse_static_write,
)
from custom_components.ha_govee_led_ble.light_services import (
    _SET_SEGMENT_COLOR_TEMP_SCHEMA,
    async_register_light_services,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum


@pytest.mark.parametrize("segments,kelvin", [([], 3000), ([16], 3000), ([True], 3000), ([1], 1999), ([1], 9001)])
async def test_preflight_keeps_preview_and_control_untouched(hass, monkeypatch, segments, kelvin):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    light = GoveeBLELight(coordinator)
    preview = AsyncMock()
    monkeypatch.setattr(light, "_async_supersede_preview", preview)
    monkeypatch.setattr(coordinator, "send_command", AsyncMock())
    monkeypatch.setattr(coordinator, "async_refresh_segments", AsyncMock())
    with pytest.raises(ServiceValidationError):
        await light.async_set_segment_color_temp(segments, kelvin)
    preview.assert_not_awaited()
    coordinator.send_command.assert_not_awaited()
    coordinator.async_refresh_segments.assert_not_awaited()
    assert coordinator.control_write_attempts == 0


def test_schema_and_effective_profile_validation():
    schema = vol.Schema(_SET_SEGMENT_COLOR_TEMP_SCHEMA)
    assert schema({"segments": ["1"], "color_temp_kelvin": "3000"}) == {
        "segments": [1],
        "color_temp_kelvin": 3000,
    }
    with pytest.raises(vol.Invalid):
        schema({"segments": [1], "color_temp_kelvin": 3000.5})
    profile = replace(get_profile("H617A"), segment_count=5, min_color_temp_kelvin=2700)
    for segments, kelvin in (([6], 3000), ([1], 2600), ([1], True), ([1], 3000.5)):
        with pytest.raises(ValueError):
            build_segment_color_temp(segments, kelvin, profile=profile)
    parsed = parse_static_write(build_segment_color_temp([1, 5], 3000, profile=profile))
    assert parsed is not None
    assert (parsed.segment_mask, parsed.kelvin, parsed.kelvin_companion_rgb) == (17, 3000, (255, 177, 109))
    # Direct-device write used an explicitly supplied companion, not kelvin_to_rgb().
    assert build_colour_temperature(3000, (255, 185, 105), 1) == bytes.fromhex(
        "330515010000000bb8ffb96901000000000000bf"
    )


def test_service_registration_uses_shared_segment_schema():
    with patch(
        "custom_components.ha_govee_led_ble.light_services.service.async_register_platform_entity_service"
    ) as register:
        async_register_light_services(MagicMock())
    calls = [item for item in register.call_args_list if item.args[2] == "set_segment_color_temp"]
    assert len(calls) == 1
    assert calls[0].kwargs["func"] == "async_set_segment_color_temp"
    assert calls[0].kwargs["schema"] is _SET_SEGMENT_COLOR_TEMP_SCHEMA


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "missing",
        "ignored",
        "mismatch",
        "sibling",
        "selected_brightness",
        "sibling_brightness",
        "applied_then_error",
        "before_write",
        "preflight_missing",
        "preflight_partial",
        "preflight_error",
    ],
)
async def test_masked_kelvin_requires_fresh_rgb_and_preserves_siblings(hass, monkeypatch, virtual_clock, failure):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.install_static_color(kelvin=4000)
    # Even an old observed cache is not the baseline for sibling preservation.
    coordinator.segment_colors = [(255, 255, 255)] * 15
    coordinator.segment_state_source = "observed"
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    writes = []
    original_colors = [(255, 205, 166)] * 14 + [(3, 4, 5)]
    original_brightness = list(range(20, 35))
    colors = list(original_colors)
    brightness = list(original_brightness)

    async def transmit(_uuid, packet, **_kwargs):
        if packet[0] == 0x33:
            writes.append(packet)
            assert coordinator.segment_state_source == "optimistic"
            assert coordinator._field_revisions.get("segment_colors", 0) > 0
            if failure != "ignored":
                colors[0] = (255, 177, 109)
            if failure == "mismatch":
                colors[0] = (0, 0, 255)
            elif failure == "sibling":
                colors[-1] = (255, 255, 255)  # matches stale cache, not the fresh baseline
            elif failure == "selected_brightness":
                brightness[0] = 100
            elif failure == "sibling_brightness":
                brightness[-1] = 100
            elif failure == "applied_then_error":
                raise BleakError("applied before radio failure")
            return
        assert packet[:2] == b"\xaa\xa5"
        if failure == "preflight_error":
            raise BleakError("cannot read baseline")
        if failure == "preflight_missing" or (writes and failure == "missing"):
            return
        page = packet[2]
        if failure == "preflight_partial" and page == 5:
            return
        # Synthetic physical-state replies exercise the real complete-page refresh/provenance.
        payload = (
            bytes([0xAA, 0xA5, page])
            + b"".join(bytes([brightness[index], *colors[index]]) for index in range((page - 1) * 3, page * 3))
            + bytes(4)
        )
        coordinator._notify_callback(None, bytearray(payload + bytes([xor_checksum(payload)])))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    if failure == "before_write":
        coordinator.profile = replace(coordinator.profile, outbound_transform=lambda p: b"" if p[0] == 0x33 else p)
    refresh = coordinator.async_refresh_segments

    async def refresh_quickly():
        return await refresh(timeout=0.01)

    monkeypatch.setattr(coordinator, "async_refresh_segments", AsyncMock(side_effect=refresh_quickly))
    if failure:
        with pytest.raises(HomeAssistantError) as exc:
            await light.async_set_segment_color_temp([1], 3000)
        assert exc.value.translation_key == (
            "invalid_segments" if failure == "before_write" else "device_command_failed"
        )
    else:
        await light.async_set_segment_color_temp([1], 3000)
    if failure and failure.startswith("preflight_"):
        assert writes == [] and coordinator.control_write_attempts == 0
        assert coordinator._field_revisions.get("segment_colors", 0) == 0
        coordinator.async_refresh_segments.assert_awaited_once_with()
    elif failure == "before_write":
        assert writes == [] and coordinator.segment_state_source == "observed"
        coordinator.async_refresh_segments.assert_awaited_once_with()
        assert coordinator.segment_colors == original_colors
        assert coordinator.segment_brightness == original_brightness
    else:
        assert len(writes) == 1
        parsed = parse_static_write(writes[0])
        assert parsed is not None and parsed.kelvin == 3000 and parsed.segment_mask == 1
        assert coordinator.segment_state_source == ("optimistic" if failure == "missing" else "observed")
        if failure != "missing":
            assert coordinator.color_temp_kelvin is None
            assert coordinator.segment_colors == colors
            assert coordinator.segment_brightness == brightness
        if failure is None:
            assert colors == [(255, 177, 109)] + original_colors[1:]
            assert brightness == original_brightness
            assert coordinator.async_refresh_segments.await_count == 1


@pytest.mark.parametrize(
    "failure",
    [None, "non_white", "disagreeing_selected", "sibling", "wrong_kelvin"],
)
async def test_h66a0_segment_kelvin_confirms_device_rendered_rgb_and_mode_kelvin(
    hass, monkeypatch, virtual_clock, failure
):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H66A0", configuration_url=None)
    light = GoveeBLELight(coordinator)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", MagicMock())
    monkeypatch.setattr(coordinator, "_disconnect_locked", AsyncMock())
    colors = [(10, 20, 30)] * 14
    brightness = [80] * 14

    async def transmit(_uuid, packet, **_kwargs):
        if packet[0] == 0x33:
            colors[0] = (0, 0, 255) if failure == "non_white" else (255, 157, 51)
            colors[1] = (255, 180, 90) if failure == "disagreeing_selected" else (255, 157, 51)
            if failure == "sibling":
                colors[2] = (99, 99, 99)
            elif failure == "wrong_kelvin":
                colors[:] = [(255, 157, 51)] * 14
            return
        if packet[:2] == b"\xaa\x05":
            kelvin_hex = "0fa0" if failure == "wrong_kelvin" else "0000"
            frame = bytes.fromhex(f"aa051500{kelvin_hex}").ljust(19, b"\x00")
            coordinator._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))
            return
        assert packet[:2] == b"\xaa\xa5"
        page = packet[2]
        start = (page - 1) * 4
        end = min(page * 4, 14)
        records = b"".join(bytes([brightness[i], *colors[i]]) for i in range(start, end))
        payload = (bytes([0xAA, 0xA5, page]) + records).ljust(19, b"\x00")
        coordinator._notify_callback(None, bytearray(payload + bytes([xor_checksum(payload)])))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    if failure:
        with pytest.raises(HomeAssistantError):
            await light.async_set_segment_color_temp(list(range(1, 15)) if failure == "wrong_kelvin" else [1, 2], 3000)
    else:
        await light.async_set_segment_color_temp([1, 2], 3000)
        assert coordinator.color_temp_kelvin is None
        assert coordinator.segment_colors[:2] == [(255, 157, 51), (255, 157, 51)]


@pytest.mark.parametrize(
    "model,whole,segments,requested",
    [
        ("H66A0", True, None, 3000),
        ("H66A0", False, [8, 9], 3000),
        ("H66A0", False, list(range(1, 15)), 3000),
        ("H1A42", False, [4], 3000),
        ("H61F5", True, None, 3000),
        ("H61F5", False, [4], 3000),
        ("H61F5", True, None, 3050),
        ("H1A42", True, None, 3050),
    ],
)
@pytest.mark.parametrize("settling", [0, 0.35, 2.8])
async def test_issue_429_six_operations_settle_without_replaying_kelvin(
    hass, monkeypatch, virtual_clock, model, whole, segments, requested, settling
):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    c.is_on = True

    def reply(domain, body):
        frame = bytes([0xAA, domain, *body]).ljust(19, b"\0")
        c._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))

    if model == "H61F5":
        reply(0x40, [0, 21])
    count = c.profile.segment_count
    selected = set(range(count)) if segments is None else {n - 1 for n in segments}
    colors = [(255, 255, 255)] * count
    brightness = [70 + index for index in range(count)]
    actual_kelvin = ((requested + 50) // 100) * 100
    rendered = (255, 157, 51) if model == "H66A0" else (255, 185, 105) if actual_kelvin == 3000 else (255, 189, 111)
    writes = []
    written_at = None
    retained_during_transition = []

    async def transmit(_uuid, packet, **_kwargs):
        nonlocal written_at
        if packet[0] == 0x33:
            writes.append(packet)
            written_at = asyncio.get_running_loop().time()
            return
        if packet[1] == 5:
            kelvin = actual_kelvin if model in {"H66A0", "H1A42"} and len(selected) == count else 0
            reply(5, [0x15, 0, *kelvin.to_bytes(2, "big")])
        elif packet[1] == 0xA5:
            page = packet[2]
            transient = written_at is not None and asyncio.get_running_loop().time() < written_at + settling
            if written_at is not None:
                for index in selected:
                    colors[index] = (0, 0, 0) if transient else rendered
            start = (page - 1) * 4
            body = [page]
            for index in range(start, min(start + 4, count)):
                body.extend([brightness[index], *colors[index]])
            reply(0xA5, body)
            if model == "H61F5" and whole and transient:
                retained_during_transition.append(c.color_temp_kelvin)
        elif packet[1] == 1:
            reply(1, [1])
        elif packet[1] == 4:
            reply(4, [50])

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    light = GoveeBLELight(c)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    if whole:
        await light.async_turn_on(color_temp_kelvin=requested)
    else:
        await light.async_set_segment_color_temp(segments, requested)
    assert len(writes) == 1
    static = parse_static_write(writes[0], model, profile=c.profile)
    assert static is not None and static.segment_mask == sum(1 << i for i in selected)
    assert static.kelvin == actual_kelvin
    await asyncio.sleep(settling)
    assert await c.async_refresh_segments()
    assert c.segment_colors == [rendered if i in selected else (255, 255, 255) for i in range(count)]
    assert c.segment_brightness == brightness
    if whole and model == "H61F5":
        reply(5, [0x15, 0, 0, 0])
        assert light.color_temp_kelvin == actual_kelvin and c.color_temp_kelvin_source == "retained"
        assert not c._field_revisions.get("color_temp_kelvin", 0)
        assert all(kelvin == actual_kelvin for kelvin in retained_during_transition)
    if not whole and len(selected) != count:
        assert c.color_temp_kelvin is None


@pytest.mark.parametrize("model", ["H66A0", "H1A42", "H61F5"])
async def test_native_white_recovery_requires_known_rgb_intent(hass, monkeypatch, model):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    c.is_on = True
    c.color_mode = ParsedMode.COLOUR
    c.segment_state_source = "observed"
    state = c.capture_effect_control_state()
    assert not state.static_rgb_known
    send = AsyncMock()
    monkeypatch.setattr(c, "send_command", send)
    assert not await c.async_restore_effect_control_state(state, overwritten_diy_code=None)
    send.assert_not_awaited()
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    await c._async_write_packet(client, build_color_rgb(10, 20, 30, model), arm_expected=True)
    assert not c.capture_effect_control_state().static_rgb_known
    for page in range(1, c.profile.segment_group_count + 1):
        frame = bytes([0xAA, 0xA5, page])
        start = (page - 1) * 4
        frame += b"".join(bytes([100, 10, 20, 30]) for _ in range(start, min(start + 4, c.profile.segment_count)))
        frame = frame.ljust(19, b"\0")
        c._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))
    captured = c.capture_effect_control_state()
    assert captured.static_rgb_known
    assert type(captured).from_dict(captured.to_dict()).static_rgb_known
    c._clear_client_state(client)
    assert not c.capture_effect_control_state().static_rgb_known


@pytest.mark.parametrize("failure", ["subscription", "profile", "partial", "cancel", "blocked_write"])
async def test_kelvin_transaction_aborts_without_reconnect_or_replay(hass, monkeypatch, virtual_clock, failure):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H1A42", configuration_url=None)
    writes = []
    started = asyncio.get_running_loop().time()

    async def transmit(_uuid, packet, **_kwargs):
        if packet[0] == 0x33:
            writes.append(packet)
            if failure == "blocked_write":
                await asyncio.sleep(60)
            return
        if packet[1] == 5:
            body = bytes.fromhex("15000000")
        else:
            page = packet[2]
            if writes and page == 2:
                if failure == "partial":
                    return
                if failure == "cancel":
                    raise asyncio.CancelledError
                if failure == "subscription":
                    c._notification_token = object()
                if failure == "profile":
                    c._profile_generation += 1
            body = bytes([page]) + bytes([80, 255, 255, 255]) * (4 if page == 1 else 1)
        frame = (bytes([0xAA, packet[1]]) + body).ljust(19, b"\0")
        c._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    light = GoveeBLELight(c)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else HomeAssistantError):
        await light.async_set_segment_color_temp([4], 3000)
    assert len(writes) == 1
    c._ensure_connected.assert_awaited_once()
    assert asyncio.get_running_loop().time() - started <= 5.01
    if failure in {"partial", "cancel"}:
        assert c._segment_query_incomplete


@pytest.mark.parametrize("rendered", [(0, 0, 0), (0, 0, 255)])
async def test_failed_whole_kelvin_discards_contradicted_intent(hass, monkeypatch, virtual_clock, rendered):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H61F5", configuration_url=None)
    c.is_on = True
    c.color_mode = ParsedMode.COLOUR
    c.install_static_color(kelvin=4000, source="observed")
    writes = []

    async def transmit(_uuid, packet, **_kwargs):
        if packet[0] == 0x33:
            writes.append(packet)
            return
        body = bytes.fromhex("15000000")
        if packet[1] == 0xA5:
            page = packet[2]
            color = rendered if writes else (255, 255, 255)
            start = (page - 1) * 4
            body = bytes([page]) + bytes([80, *color]) * min(4, c.profile.segment_count - start)
        frame = (bytes([0xAA, packet[1]]) + body).ljust(19, b"\0")
        c._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    light = GoveeBLELight(c)
    monkeypatch.setattr(light, "_async_supersede_preview", AsyncMock())
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(color_temp_kelvin=3000)
    assert len(writes) == 1
    assert c.color_temp_kelvin is None and c.color_temp_kelvin_source == "initial"
    assert c.segment_colors == [rendered] * c.profile.segment_count


async def test_failed_rgb_write_cannot_qualify_matching_native_white_as_rgb(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H61F5", configuration_url=None)
    c.is_on = True
    c.color_mode = ParsedMode.COLOUR
    c.install_static_color(kelvin=3000, source="retained")
    rgb = (255, 185, 105)
    writes = []

    async def transmit(_uuid, packet, **_kwargs):
        if packet[0] == 0x33:
            writes.append(packet)
            raise TimeoutError("RGB was not delivered")
        page = packet[2]
        start = (page - 1) * 4
        frame = bytes([0xAA, 0xA5, page]) + bytes([80, *rgb]) * min(4, c.profile.segment_count - start)
        frame = frame.ljust(19, b"\0")
        c._notify_callback(None, bytearray(frame + bytes([xor_checksum(frame)])))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=transmit))
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(c, "_renew_foreground_lease", MagicMock())
    with pytest.raises(TimeoutError, match="not delivered"):
        await c.send_command(build_color_rgb(*rgb, c.model))
    state = c.capture_effect_control_state()
    assert state.segment_colors == (rgb,) * c.profile.segment_count
    assert not state.static_rgb_known
    assert not await c.async_restore_effect_control_state(state, overwritten_diy_code=None)
    assert len(writes) == 1


async def test_h66a0_kelvin_restore_refuses_to_widen_masked_kelvin_to_whole_strip(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H66A0", configuration_url=None)
    coordinator.is_on = True
    coordinator.brightness_pct = 80
    coordinator.color_mode = ParsedMode.COLOUR
    coordinator.color_temp_kelvin = 3000
    coordinator.segment_colors = [(255, 157, 51)] * 14
    coordinator.segment_brightness = [80] * 14
    coordinator.segment_state_source = "observed"
    state = coordinator.capture_effect_control_state()
    send_command = AsyncMock()
    monkeypatch.setattr(coordinator, "send_command", send_command)

    assert await coordinator.async_restore_effect_control_state(state, overwritten_diy_code=None) is False
    send_command.assert_not_awaited()
