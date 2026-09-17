"""Positive Pact 1 evidence narrows H6199; hardware versions never choose Pact."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from custom_components.ha_govee_led_ble.const import (
    DOMAIN,
    H6199_PACT1_PROFILE,
    MODEL_PROFILES,
    device_profile,
)
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_catalogue import MODEL_EFFECT_CATALOGUES, resolve_catalogue_template
from custom_components.ha_govee_led_ble.effect_compiler import compatibility, compile_application
from custom_components.ha_govee_led_ble.effect_contracts import device_effect_capabilities
from custom_components.ha_govee_led_ble.effect_deployments import PriorControlState
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.effect_websocket import ws_editor_devices, ws_scene_catalogue_list
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_firmware_query,
    build_h6199_control,
    build_hardware_query,
    build_power,
    build_power_query,
    build_segment_query,
    build_subordinate_query,
    build_video_mode,
    build_white_balance,
    require_profile_packet,
)
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb
from tests.test_h6199_capabilities import lifecycle as pact_lifecycle  # noqa: F401
from tests.test_h6199_native_controls import frame


def advertise(c, pact):
    c._note_advertisement(SimpleNamespace(manufacturer_data={34818: bytes((0xEC, 0, pact, 1, 0))}))


@pytest.mark.parametrize("model", ["H6199", "H6099", "H617A"])
def test_only_exact_model_and_positive_pact_select_restriction(model):
    assert device_profile(model, None, None) is MODEL_PROFILES[model]
    assert device_profile(model, 2, 1) is MODEL_PROFILES[model]
    assert device_profile(model, 1, 1) is (H6199_PACT1_PROFILE if model == "H6199" else MODEL_PROFILES[model])


@pytest.mark.parametrize(
    "builder",
    [
        lambda: build_power(True, "H6199"),
        lambda: build_power(False, "H6199"),
        lambda: build_power_query("H6199"),
        lambda: build_firmware_query("H6199"),
        lambda: build_hardware_query("H6199"),
    ],
)
def test_generated_guard_permits_power_and_main_identity(builder):
    require_profile_packet(builder(), H6199_PACT1_PROFILE)


@pytest.mark.parametrize(
    "packet",
    [
        build_brightness(50, "H6199"),
        build_brightness_query("H6199"),
        build_colour_mode_query("H6199"),
        build_color_rgb(1, 2, 3, "H6199"),
        build_video_mode("movie", True, 50, False, 50, "H6199"),
        build_h6199_control("gradient", 1),
        build_white_balance(21, 5, "H6199"),
        build_segment_query(1, "H6199"),
        build_subordinate_query(0x20, "H6199"),
        b"invalid upload",
    ],
)
async def test_physical_boundary_rejects_before_optimism(hass, monkeypatch, packet):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    advertise(c, 1)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    monkeypatch.setattr(c, "_ensure_connected", AsyncMock(return_value=client))
    before = c.capture_effect_control_state()
    with pytest.raises(ValueError, match="does not support this operation"):
        await c.async_write_effect_sequence((packet,), intent=ControlIntent.USER, state_values={"brightness_pct": 254})
    assert c.capture_effect_control_state() == before
    assert c.control_write_attempts == 0 and not c._expected_state
    client.write_gatt_char.assert_not_awaited()


async def test_known_pact1_real_setup_and_power(pact_lifecycle):  # noqa: F811
    c, replies, clients, packets = pact_lifecycle
    advertise(c, 1)
    replies[build_hardware_query(c.model)] = frame("aa0703" + b"1.00.01".hex())
    replies[build_firmware_query(c.model)] = frame("aa06" + b"1.07.02".hex())
    await c._async_update_data()
    assert c.available and c.is_on
    assert c.profile is H6199_PACT1_PROFILE
    assert set(packets) == {build_power_query(c.model), build_hardware_query(c.model), build_firmware_query(c.model)}
    # Main identity replies may arrive just after the power reply; neither is mandatory.
    assert c.hw_version == "1.00.01" and c.fw_version == "1.07.02"
    light = GoveeBLELight(c)
    assert light.supported_color_modes == {ColorMode.ONOFF} and light.brightness is None
    before = c.capture_effect_control_state()
    for reply in ("aa04fe", "aa0513046400012060a0", "aaa90006011003001505", "aaae0104141e2832"):
        c._notify_callback(None, bytearray(frame(reply)))
    assert c.capture_effect_control_state() == before
    assert PriorControlState.from_dict(before.to_dict()) == before
    await c.send_command(build_power(False, c.model))
    assert packets[-1] == build_power(False, c.model)


async def test_late_pact_changes_capabilities_without_destroying_library(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c.hw_version, c.fw_version = "1.00.01", "1.07.02"
    assert c.profile is MODEL_PROFILES[c.model]
    light = GoveeBLELight(c)
    items = tuple(LibraryItem.new(t.label, t.content) for t in MODEL_EFFECT_CATALOGUES[c.model].templates)
    light._library_snapshot = LibrarySnapshot(items)
    before = [item.to_dict() for item in items]
    c.brightness_pct = 254
    advertise(c, 1)
    assert c.brightness_pct == 100 and light.brightness is None and light.color_mode is ColorMode.ONOFF
    assert light.effect_list == [] and light._selector_entries() == ()
    assert not light.supported_features
    for item in items:
        assert compatibility(item, c.model, profile=c.profile).state == "incompatible"
        with pytest.raises(ValueError):
            compile_application(item, c.model, profile=c.profile)
    for template in MODEL_EFFECT_CATALOGUES[c.model].templates:
        with pytest.raises(ValueError, match="no effect templates"):
            resolve_catalogue_template(c.model, template.id, profile=c.profile)
    catalogue = MODEL_EFFECT_CATALOGUES[c.model].to_dict(profile=c.profile)
    assert catalogue["templates"] == catalogue["workflows"] == catalogue["music_modes"] == []
    capabilities = device_effect_capabilities("entry", c.model, "Test", 0, profile=c.profile).to_dict()
    assert capabilities["effect_categories"] == []
    assert set(capabilities["custom_effects"].values()) == {"unsupported"}
    assert set(capabilities["profiles"].values()) == {"unsupported"}
    c._note_advertisement(SimpleNamespace(manufacturer_data={}))
    assert c.profile is H6199_PACT1_PROFILE
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    with pytest.raises(HomeAssistantError):
        await light._async_turn_on(brightness=200)
    client.write_gatt_char.assert_not_awaited()
    advertise(c, 2)
    assert c.profile is MODEL_PROFILES[c.model]
    assert ColorMode.RGB in light.supported_color_modes and light.color_mode is ColorMode.RGB
    assert len(c.segment_colors) == 15 and c.segment_state_source == "initial"
    assert light.effect_list
    assert [item.to_dict() for item in items] == before


async def test_editor_excludes_restricted_device(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    advertise(c, 1)
    entry = SimpleNamespace(runtime_data=c, state=ConfigEntryState.LOADED, domain=DOMAIN, entry_id="entry")
    monkeypatch.setattr(hass.config_entries, "async_entries", lambda _=None: [entry] if _ == DOMAIN else [])
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda _: entry)
    monkeypatch.setattr("custom_components.ha_govee_led_ble.effect_websocket._backend", lambda _: MagicMock())
    connection = MagicMock()
    await ws_editor_devices.__wrapped__(hass, connection, {"id": 1})
    connection.send_result.assert_called_once_with(1, {"devices": []})
    ws_scene_catalogue_list(hass, connection, {"id": 2, "config_entry_id": "entry"})
    connection.send_error.assert_called_once_with(2, "unsupported_model", "Device profile supports no scenes")


@pytest.mark.parametrize("change_at", ["connect", "guard"])
async def test_late_pact_identification_blocks_prepared_write(hass, monkeypatch, change_at):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    packet = build_brightness(50, c.model)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def connect():
        if change_at == "connect":
            advertise(c, 1)
        return client

    def guard():
        if change_at == "guard":
            advertise(c, 1)

    monkeypatch.setattr(c, "_ensure_connected", connect)
    with pytest.raises(ValueError, match="does not support this operation"):
        await c.async_write_effect_sequence(
            (packet,), intent=ControlIntent.USER, write_guard=guard, state_values={"brightness_pct": 254}
        )
    assert c.brightness_pct == 100 and c.control_write_attempts == 0
    client.write_gatt_char.assert_not_awaited()


async def test_late_pact_does_not_rollback_invalid_state(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    c.brightness_pct = 254
    c.is_on = True
    light = GoveeBLELight(c)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def connect():
        advertise(c, 1)
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    with pytest.raises(HomeAssistantError):
        await light._async_turn_on(brightness=200)
    assert c.brightness_pct == 100
    assert PriorControlState.from_dict(c.capture_effect_control_state().to_dict()).brightness_pct == 100
    client.write_gatt_char.assert_not_awaited()
