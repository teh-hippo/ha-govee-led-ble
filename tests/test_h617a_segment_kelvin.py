"""Masked Kelvin service: real writer, direct-device replay, and failure boundaries."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from bleak import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.ha_govee_led_ble.const import get_profile
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_colour_temperature
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_segment_color_temp, parse_static_write
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
async def test_masked_kelvin_requires_fresh_rgb_and_preserves_siblings(hass, monkeypatch, failure):
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
            assert coordinator.async_refresh_segments.await_count == 2
