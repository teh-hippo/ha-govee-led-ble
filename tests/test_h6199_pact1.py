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
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode
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
from custom_components.ha_govee_led_ble.light_commands import (
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
)
from custom_components.ha_govee_led_ble.protocol_h6199 import build_h6199_control
from custom_components.ha_govee_led_ble.transport import WRITE_UUID
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
    packet = builder()
    require_profile_packet(packet, H6199_PACT1_PROFILE)
    transform = H6199_PACT1_PROFILE.outbound_transform
    assert transform is not None and transform(packet) == packet


@pytest.mark.parametrize(("percent", "register"), [(1, 20), (50, 136), (100, 254)])
def test_brightness_reencodes_the_register_without_changing_logical_expectations(percent, register):
    profile = H6199_PACT1_PROFILE
    packet = build_brightness(percent, "H6199", profile=profile)
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(packet) == frame(f"3304{register:02x}")
    assert expectations_from_packet(packet, "H6199", profile=profile) == {"brightness_pct": percent}


def test_rgb_reuses_the_shared_logical_command_and_expectations():
    profile = H6199_PACT1_PROFILE
    packet = build_color_rgb(32, 96, 160, "H6199", profile=profile)
    assert packet == build_color_rgb(32, 96, 160, "H6199")
    require_profile_packet(packet, profile)
    transform = profile.outbound_transform
    assert transform is not None
    assert transform(packet) == bytes.fromhex("33050b2060a00000ff7f0000000000000000005d")
    assert expectations_from_packet(packet, "H6199", profile=profile) == {
        "color_mode": (ParsedMode.COLOUR, None),
        "rgb_color": (32, 96, 160),
    }


@pytest.mark.parametrize(
    "packet",
    [
        build_brightness_query("H6199"),
        build_colour_mode_query("H6199"),
        build_color_temp(4000, "H6199"),
        build_segment_color([1], 1, 2, 3, "H6199"),
        build_segment_brightness([1], 50, "H6199"),
        frame("330515ff"),
        build_brightness(0, "H6199"),
        frame("330465"),
        build_brightness(50, "H6199")[:-1] + b"\x00",
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
    with pytest.raises(ValueError):
        await c.async_write_effect_sequence((packet,), intent=ControlIntent.USER, state_values={"brightness_pct": 254})
    assert c.capture_effect_control_state() == before
    assert c.control_write_attempts == 0 and not c._expected_state
    client.write_gatt_char.assert_not_awaited()


async def test_known_pact1_real_setup_and_basic_controls(pact_lifecycle, monkeypatch):  # noqa: F811
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
    assert light.supported_color_modes == {ColorMode.RGB} and light.brightness is not None
    before = c.capture_effect_control_state()
    for reply in ("aa040a", "aa04fe", "aa0513046400012060a0", "aaa90006011003001505", "aaae0104141e2832"):
        c._notify_callback(None, bytearray(frame(reply)))
    assert c.capture_effect_control_state() == before
    assert PriorControlState.from_dict(before.to_dict()) == before
    monkeypatch.setattr(light, "_notify_state_changed", MagicMock())
    packets.clear()
    await light._async_turn_on(brightness=128, rgb_color=(32, 96, 160))
    assert [packet for packet in packets if packet[0] == 0x33] == [
        frame("330488"),
        bytes.fromhex("33050b2060a00000ff7f0000000000000000005d"),
    ]
    assert all(packet[:2] not in (b"\xaa\x04", b"\xaa\x05", b"\xaa\xa5") for packet in packets)
    assert c.brightness_pct == 50 and c.rgb_color == (32, 96, 160)
    assert c.rgb_color_source == "optimistic" and c.color_mode is ParsedMode.COLOUR
    assert c._expected_state["brightness_pct"][0] == 50
    assert c._expected_state["rgb_color"][0] == (32, 96, 160)
    assert c._field_revisions.get("rgb_color", 0) == 0
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
    assert c.brightness_pct == 100 and light.brightness == 255 and light.color_mode is ColorMode.RGB
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
        await light._async_turn_on(color_temp_kelvin=4000)
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
    packet = build_video_mode("movie", True, 50, False, 50, c.model)
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


async def test_prepared_rgb_reencodes_after_pact_identification_during_connect(hass, monkeypatch):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    packet = build_color_rgb(32, 96, 160, c.model)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client

    async def connect():
        advertise(c, 1)
        return client

    monkeypatch.setattr(c, "_ensure_connected", connect)
    await c.send_command(packet)
    client.write_gatt_char.assert_awaited_once_with(
        WRITE_UUID, bytes.fromhex("33050b2060a00000ff7f0000000000000000005d"), response=False
    )
    assert c.rgb_color == (32, 96, 160) and c.rgb_color_source == "optimistic"


@pytest.mark.parametrize("packet", [build_brightness(50, "H6199"), build_color_rgb(32, 96, 160, "H6199")])
async def test_pact_change_after_encoding_rejects_before_optimism(hass, packet):
    c = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url=None)
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    c._client = client
    with pytest.raises(ValueError, match="profile changed"):
        await c._async_write_packet(client, packet, arm_expected=True, before_write=lambda: advertise(c, 1))
    client.write_gatt_char.assert_not_awaited()
    assert c.control_write_attempts == 0 and not c._expected_state
    assert c.brightness_pct == 100 and c.rgb_color_source == "initial"


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
        await light._async_turn_on(color_temp_kelvin=4000)
    assert c.brightness_pct == 100
    assert PriorControlState.from_dict(c.capture_effect_control_state().to_dict()).brightness_pct == 100
    client.write_gatt_char.assert_not_awaited()
