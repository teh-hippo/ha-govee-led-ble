"""Synthetic transport checks, not H6099 hardware qualification."""

import asyncio
import json
import logging
import os
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakError
from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dbus_fast.constants import MessageType
from habluetooth.wrappers import HaBleakClientWrapper
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble import light as light_platform
from custom_components.ha_govee_led_ble import switch as switch_platform
from custom_components.ha_govee_led_ble.advertisement import parse_govee_advertisement
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness_query,
    build_power,
    build_power_query,
)
from custom_components.ha_govee_led_ble.govee_encryption import (
    KEY_COMMUNICATION,
    KEY_HANDSHAKE,
    GoveeCryptoError,
    GoveeTransportError,
    build_v2_handshake,
    parse_v1_handshake,
    parse_v2_handshake,
    parse_wire,
    seal,
    unseal,
    v1_transform,
)
from custom_components.ha_govee_led_ble.govee_encryption import session as session_module
from custom_components.ha_govee_led_ble.govee_encryption.session import GoveeEncryptionSession
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_segment_color
from custom_components.ha_govee_led_ble.music_commands import prepare_music_request
from custom_components.ha_govee_led_ble.transport import (
    ENCRYPTION_UUID,
    READ_UUID,
    WRITE_UUID,
    fragment_a3,
    xor_checksum,
)
from tests.coordinator_test_support import _packet

KEY = bytes(range(16))
IV = bytes(range(8))
M = "custom_components.ha_govee_led_ble.coordinator"


async def test_wire_parsing_does_not_import_on_event_loop():
    with patch(
        "custom_components.ha_govee_led_ble.govee_encryption.import_module",
        side_effect=AssertionError("Runtime protocol import blocks the event loop"),
    ):
        assert parse_wire("Marker", b"\x01\x01").version == 1


@pytest.mark.parametrize("pact_type", [1, 2])
async def test_h607c_marker_qualifies_rgb_only_for_current_connection(hass, monkeypatch, pact_type):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    device = client(bytes((2, 0, 0, 0, pact_type, 1)))
    coordinator.is_on = True
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", lambda: None)
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(return_value=device))
    monkeypatch.setattr(coordinator, "_start_keep_alive", lambda: None)
    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.entity_id = "light.h607c"
    await light.async_turn_on(rgb_color=(12, 34, 56))
    assert (coordinator.pact_type, coordinator.pact_code) == (pact_type, 1)
    assert device.write_gatt_char.await_args.args[1] == build_color_rgb(
        12, 34, 56, "H607C", profile=coordinator.profile
    )
    assert coordinator.segment_state_source == "optimistic"
    await light.async_set_segment_color([13], (90, 120, 200))
    assert device.write_gatt_char.await_args.args[1] == build_segment_color(
        [13], 90, 120, 200, "H607C", profile=coordinator.profile
    )
    coordinator._clear_client_state(device)
    assert coordinator.pact_type is None and not coordinator.profile.supports_rgb
    assert coordinator.h607c_pact_readiness == "stale"
    assert coordinator.native_presentation_profile.supports_rgb
    assert ColorMode.RGB in light.supported_color_modes


async def test_h607c_scanner_pact_conflict_fails_closed(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)

    def record(payload, source, timestamp):
        return SimpleNamespace(
            name="Govee_H607C",
            address=coordinator.address,
            source=source,
            time=timestamp,
            manufacturer_data={0x8843: bytes.fromhex(payload)},
        )

    now = time.monotonic()
    records = [record("ec00010100", "scanner-a", now)]
    monkeypatch.setattr(
        f"{M}.bluetooth.async_last_service_info", lambda *args, **kwargs: records[0] if records else None
    )
    coordinator._refresh_h607c_advertisements()
    assert coordinator.profile.supports_rgb and coordinator.h607c_pact_readiness == "ready"
    coordinator._note_advertisement(record("ec00020100", "scanner-b", now))
    coordinator._refresh_h607c_advertisements()
    assert coordinator.h607c_pact_readiness == "conflicting"
    assert not coordinator.profile.supports_rgb and not coordinator.native_presentation_profile.supports_rgb
    generation = coordinator._profile_generation
    coordinator.brightness_pct = 37
    coordinator._async_on_advertisement(records[0], None)
    assert coordinator._profile_generation == generation and coordinator.brightness_pct == 37
    coordinator._h607c_advertisement_observations["scanner-b"] = (now - 1000, frozenset({(2, 1)}))
    coordinator._refresh_h607c_advertisements()
    assert coordinator.profile.supports_rgb and coordinator.h607c_pact_readiness == "ready"
    records[0].time = now - 1000
    coordinator._h607c_advertisement_observations["scanner-a"] = (now - 1000, frozenset({(1, 1)}))
    records.clear()
    coordinator._refresh_h607c_advertisements()
    assert not coordinator.profile.supports_rgb and coordinator.h607c_pact_readiness == "missing"


async def test_h607c_live_equal_timestamp_cannot_be_overwritten_by_cached_pact(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    timestamp = time.monotonic()
    cached = SimpleNamespace(
        name="Govee_H607C",
        address=coordinator.address,
        source="scanner-a",
        time=timestamp,
        manufacturer_data={0x8843: bytes.fromhex("ec00010100")},
    )
    incoming = SimpleNamespace(
        name=cached.name,
        address=cached.address,
        source=cached.source,
        time=timestamp,
        manufacturer_data={0x8843: bytes.fromhex("ec00030100")},
    )
    monkeypatch.setattr(f"{M}.bluetooth.async_last_service_info", lambda *args, **kwargs: cached)
    coordinator._refresh_h607c_advertisements()
    assert coordinator.profile.supports_rgb
    coordinator._async_on_h607c_advertisement(incoming)
    assert coordinator.h607c_pact_readiness == "conflicting"
    assert not coordinator.profile.supports_rgb


async def test_h607c_advertisement_expiry_during_preflight_rejects_colour(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    info = SimpleNamespace(
        name="Govee_H607C",
        address=coordinator.address,
        source="scanner-a",
        time=time.monotonic(),
        manufacturer_data={0x8843: bytes.fromhex("ec00010100")},
    )
    monkeypatch.setattr(f"{M}.bluetooth.async_last_service_info", lambda *args, **kwargs: info)
    device = client()
    coordinator._client = device
    coordinator._notification_token = object()

    async def ensure_connected():
        coordinator._h607c_advertisement_observations["scanner-a"] = (
            time.monotonic() - 1000,
            frozenset({(1, 1)}),
        )
        return device

    async def disconnect(_client):
        device.is_connected = False
        coordinator._clear_client_state(device)

    monkeypatch.setattr(coordinator, "_ensure_connected", ensure_connected)
    monkeypatch.setattr(coordinator, "_disconnect_if_current_locked", disconnect)
    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.entity_id = "light.h607c"
    light._async_supersede_preview = AsyncMock()
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(rgb_color=(12, 34, 56))
    device.write_gatt_char.assert_not_awaited()
    light._async_supersede_preview.assert_not_awaited()
    assert not coordinator.profile.supports_rgb


@pytest.mark.parametrize("operation", ["read", "write"])
async def test_authorization_reads_are_pure_and_operations_reconcile_expired_identity(hass, monkeypatch, operation):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    device = client()
    now = time.monotonic()
    coordinator._client = device
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = now - 1
    coordinator._note_advertisement(
        SimpleNamespace(
            name="Govee_H607C",
            source="scanner",
            time=now,
            manufacturer_data={0x8843: bytes.fromhex("ec00010100")},
        )
    )
    coordinator._prune_h607c_advertisements()
    profile, generation = coordinator.profile, coordinator._authorization_generation
    assert profile.supports_rgb
    coordinator._h607c_advertisement_observations["scanner"] = (now - 1000, frozenset({(1, 1)}))
    listeners = MagicMock()
    monkeypatch.setattr(coordinator, "async_update_listeners", listeners)

    assert coordinator._authorization_profile() is profile
    assert coordinator.effect_authorization_profile is profile
    assert coordinator._authorization_generation == generation
    listeners.assert_not_called()

    if operation == "read":
        assert await coordinator._send_state_queries(
            query_brightness=False, query_color_mode=False, query_native_settings=False
        )
        device.write_gatt_char.assert_awaited_once()
    else:
        with pytest.raises(ValueError):
            await coordinator._async_write_packet(
                device, build_color_rgb(12, 34, 56, "H607C", profile=profile), arm_expected=True
            )
        device.write_gatt_char.assert_not_awaited()
    assert not coordinator.profile.supports_rgb
    assert coordinator._authorization_generation > generation
    listeners.assert_called_once()


@pytest.mark.parametrize("all_advertisements_api", [True, False])
async def test_h607c_registers_supported_advertisement_callback(hass, monkeypatch, all_advertisements_api):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    register = MagicMock(return_value=lambda: None)
    monkeypatch.setattr(f"{M}.bluetooth.async_address_present", lambda *args, **kwargs: False)
    monkeypatch.setattr(f"{M}.bluetooth.async_last_service_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(f"{M}.bluetooth.async_register_callback", register)
    monkeypatch.setattr(f"{M}.bluetooth.async_track_unavailable", lambda *args, **kwargs: lambda: None)
    if all_advertisements_api:
        register_all = MagicMock(return_value=lambda: None)
        monkeypatch.setattr(f"{M}.bluetooth.async_register_advertisement_callback", register_all)
    else:
        monkeypatch.delattr(
            "custom_components.ha_govee_led_ble.coordinator.bluetooth.async_register_advertisement_callback"
        )
    await coordinator._async_setup()
    if all_advertisements_api:
        register_all.assert_called_once()
        assert register.call_count == 1
    else:
        assert register.call_count == 2
        assert register.call_args.args[2]["connectable"] is False


async def test_h607c_revocation_during_colour_turn_on_sends_no_user_write(hass, monkeypatch, caplog):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    coordinator._h607c_advertised_pacts = {(1, 1)}
    coordinator._resolve_h607c_pact()
    device = client()
    coordinator._client = device
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = 1.0
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", lambda: None)
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    calls = 0

    async def ensure_connected():
        nonlocal calls
        calls += 1
        if calls == 2:
            coordinator._h607c_advertised_pacts = {(3, 1)}
            coordinator._resolve_h607c_pact()
        return device

    monkeypatch.setattr(coordinator, "_ensure_connected", ensure_connected)
    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.entity_id = "light.h607c"
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(rgb_color=(12, 34, 56), brightness=100)
    assert error.value.translation_key == "identity_not_ready"
    device.write_gatt_char.assert_not_awaited()
    assert not coordinator.is_on
    assert not coordinator._h607c_uncertain_state_fields
    assert "may have partially changed" not in caplog.text


@pytest.fixture
def h607c_light(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    coordinator._h607c_advertised_pacts = {(1, 1)}
    coordinator._resolve_h607c_pact()
    coordinator._present = True
    device = client()
    coordinator._client = device
    coordinator._notification_token = object()
    coordinator._notify_started_monotonic = time.monotonic()
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", lambda: None)
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=device))
    monkeypatch.setattr(coordinator, "_renew_foreground_lease", lambda: None)
    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.entity_id = "light.h607c"
    return coordinator, device, light


@pytest.mark.parametrize("confirmation", ["none", "notification", "reconcile"])
async def test_h607c_interrupted_power_reports_or_reconciles_uncertainty(
    h607c_light, monkeypatch, caplog, confirmation
):
    coordinator, device, light = h607c_light

    def observe(opcode, value):
        coordinator._notify_callback(None, bytearray(_packet(0xAA, opcode, [value])))

    async def write(_uuid, packet, **_kwargs):
        if packet == build_power(True, coordinator.model):
            coordinator._h607c_advertised_pacts = {(3, 1)}
            coordinator._resolve_h607c_pact()
            if confirmation == "notification":
                observe(1, 1)
        elif confirmation == "reconcile" and packet == build_power_query(
            coordinator.model, profile=coordinator.profile
        ):
            observe(1, 1)
        elif confirmation == "reconcile" and packet == build_brightness_query(
            coordinator.model, profile=coordinator.profile
        ):
            observe(4, 37)

    device.write_gatt_char.side_effect = write
    if confirmation == "none":
        monkeypatch.setattr(coordinator, "_refresh_connected_state", AsyncMock(return_value=False))
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(rgb_color=(12, 34, 56), brightness=100)

    assert error.value.translation_key == "partial_command"
    assert coordinator.control_write_attempts == 1
    assert device.write_gatt_char.await_count == (3 if confirmation == "reconcile" else 1)
    warnings = [record.message for record in caplog.records if "may have partially changed" in record.message]
    assert len(warnings) == 1 and "H607C" in warnings[0] and "light.h607c" in warnings[0] and "power" in warnings[0]
    assert coordinator.address not in warnings[0]
    if confirmation == "none":
        assert light.is_on is None and light.state is None and light.assumed_state
        assert light.extra_state_attributes["unconfirmed_state_fields"] == ["is_on"]
        observe(1, 0)
        assert light.is_on is False and not coordinator._h607c_uncertain_state_fields
    else:
        assert light.is_on is True and not coordinator._h607c_uncertain_state_fields
        if confirmation == "reconcile":
            assert coordinator.brightness_pct == 37


@pytest.mark.parametrize("fresh_notification", [False, True])
async def test_h607c_interrupted_brightness_preserves_only_fresh_observations(
    h607c_light, monkeypatch, caplog, fresh_notification
):
    coordinator, device, light = h607c_light
    coordinator.is_on = True
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 4, [37])))
    monkeypatch.setattr(coordinator, "_refresh_connected_state", AsyncMock(return_value=False))

    async def write(_uuid, packet, **_kwargs):
        coordinator._h607c_advertised_pacts = {(3, 1)}
        coordinator._resolve_h607c_pact()
        if fresh_notification:
            coordinator._notify_callback(None, bytearray(_packet(0xAA, 4, [50])))

    device.write_gatt_char.side_effect = write
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(rgb_color=(12, 34, 56), brightness=128)

    assert error.value.translation_key == "partial_command"
    assert coordinator.control_write_attempts == 1 and device.write_gatt_char.await_count == 1
    assert light.is_on is True
    assert "brightness request was interrupted" in caplog.text
    if fresh_notification:
        assert coordinator.brightness_pct == 50 and light.brightness == round(50 * 255 / 100)
        assert not coordinator._h607c_uncertain_state_fields
    else:
        assert light.brightness is None
        assert coordinator._h607c_uncertain_state_fields == {"brightness_pct"}
        coordinator._notify_callback(None, bytearray(_packet(0xAA, 4, [37])))
        assert light.brightness == round(37 * 255 / 100)
        assert not coordinator._h607c_uncertain_state_fields


@pytest.mark.parametrize(
    ("field", "kwargs", "opcode", "value"),
    [
        ("is_on", {"rgb_color": (12, 34, 56)}, 1, 0),
        ("brightness_pct", {"rgb_color": (12, 34, 56), "brightness": 128}, 4, 37),
    ],
)
async def test_h607c_prewrite_notification_does_not_confirm_failed_write(
    h607c_light, monkeypatch, field, kwargs, opcode, value
):
    coordinator, device, light = h607c_light
    coordinator.is_on = field != "is_on"
    connections = 0

    async def ensure_connected():
        nonlocal connections
        connections += 1
        if connections == 2:
            coordinator._notify_callback(None, bytearray(_packet(0xAA, opcode, [value])))
        return device

    monkeypatch.setattr(coordinator, "_ensure_connected", ensure_connected)
    monkeypatch.setattr(coordinator, "_refresh_connected_state", AsyncMock(return_value=False))
    device.write_gatt_char.side_effect = ValueError("write interrupted")
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(**kwargs)

    assert error.value.translation_key == "partial_command"
    assert coordinator._h607c_uncertain_state_fields == {field}
    assert (light.is_on if field == "is_on" else light.brightness) is None


async def test_h607c_transport_failure_does_not_replay_colour_write(h607c_light, monkeypatch):
    coordinator, first, light = h607c_light
    coordinator.is_on = True
    first.write_gatt_char.side_effect = BleakError("transport lost")
    second = client()

    async def ensure_connected():
        if coordinator._client is None:
            coordinator._client = second
            coordinator._notification_token = object()
        return coordinator._client

    monkeypatch.setattr(coordinator, "_ensure_connected", ensure_connected)
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(rgb_color=(12, 34, 56))

    assert error.value.translation_key == "partial_command"
    first.write_gatt_char.assert_awaited_once()
    second.write_gatt_char.assert_not_awaited()
    assert coordinator._h607c_uncertain_state_fields == {"color", "color_mode"}


@pytest.mark.parametrize("kwargs", [{"rgb_color": (12, 34, 56)}, {"color_temp_kelvin": 3200}])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_h607c_interrupted_colour_is_not_reported_as_confirmed(h607c_light, caplog, kwargs, cancelled):
    coordinator, device, light = h607c_light
    coordinator.is_on = True
    device.write_gatt_char.side_effect = asyncio.CancelledError if cancelled else ValueError("write interrupted")

    with pytest.raises(asyncio.CancelledError if cancelled else HomeAssistantError) as error:
        await light.async_turn_on(**kwargs)
    if not cancelled:
        assert error.value.translation_key == "partial_command"
    assert coordinator.control_write_attempts == 1 and device.write_gatt_char.await_count == 1
    assert light.color_mode is ColorMode.UNKNOWN and light.rgb_color is None and light.color_temp_kelvin is None
    assert light.state_attributes["color_mode"] is ColorMode.UNKNOWN
    assert light.extra_state_attributes["unconfirmed_state_fields"] == ["color", "color_mode"]
    assert light.extra_state_attributes["segment_colors"] is None
    assert light.assumed_state and "color_mode" not in coordinator._expected_state
    assert caplog.text.count("may have partially changed") == 1


async def test_h607c_unconfirmed_power_is_not_retried_during_colour_request(h607c_light, monkeypatch, caplog):
    coordinator, device, light = h607c_light
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=False))
    monkeypatch.setattr(coordinator, "_refresh_connected_state", AsyncMock(return_value=False))
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(rgb_color=(12, 34, 56))
    assert error.value.translation_key == "partial_command"
    assert coordinator.control_write_attempts == 1 and device.write_gatt_char.await_count == 1
    assert light.is_on is None and caplog.text.count("may have partially changed") == 1


async def test_h607c_missing_pact_presents_colour_but_does_not_cancel_preview(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    device = client(b"\x01\x00")
    coordinator._client = device
    coordinator._notification_token = object()
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", lambda: None)
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=device))

    async def disconnect(_client):
        device.is_connected = False
        coordinator._clear_client_state(device)

    monkeypatch.setattr(coordinator, "_disconnect_if_current_locked", disconnect)
    light = GoveeBLELight(coordinator)
    light.hass = hass
    light.entity_id = "light.h607c"
    light._async_supersede_preview = AsyncMock()
    assert {mode.value for mode in light.supported_color_modes} == {"rgb", "color_temp"}
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(rgb_color=(12, 34, 56))
    light._async_supersede_preview.assert_not_awaited()
    device.write_gatt_char.assert_not_awaited()
    assert not coordinator.is_on


async def _register_h607c_entities(hass, coordinator):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=coordinator.address, data={CONF_MODEL: "H607C"})
    entry.add_to_hass(hass)
    entry.runtime_data = coordinator
    for domain, module in (("light", light_platform), ("switch", switch_platform)):
        component = EntityComponent(logging.getLogger(__name__), domain, hass)
        platform = component._async_init_entity_platform(DOMAIN, module)
        assert await platform.async_setup_entry(entry)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    ("identity", "modes", "gradual_state"),
    [
        ("missing", {"rgb", "color_temp"}, "unknown"),
        ("stale", {"rgb", "color_temp"}, "unknown"),
        ("supported", {"rgb", "color_temp"}, "on"),
        ("unsupported", {"brightness"}, None),
        ("conflicting", {"brightness"}, None),
    ],
)
async def test_h607c_registered_entities_present_identity_states(hass, identity, modes, gradual_state):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    coordinator._present = coordinator.is_on = True
    if identity in {"missing", "stale"}:
        coordinator._h607c_marker_seen = identity == "stale"
        coordinator._resolve_device_profile()
    else:
        coordinator._h607c_advertised_pacts = (
            {(1, 1), (2, 1)} if identity == "conflicting" else {(1, 1)} if identity == "supported" else {(3, 1)}
        )
        coordinator._resolve_h607c_pact()
    if identity == "supported":
        coordinator.boolean_control_state["gradual"] = True
    entry = await _register_h607c_entities(hass, coordinator)
    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    light = next(item for item in entries if item.domain == "light")
    gradual = next((item for item in entries if item.unique_id.endswith("_gradual")), None)
    state = hass.states.get(light.entity_id)
    assert state is not None and state.state == "on"
    assert set(state.attributes["supported_color_modes"]) == modes
    assert state.attributes["color_mode"] == ("rgb" if "rgb" in modes else "brightness")
    if gradual_state is None:
        assert gradual is None
    else:
        assert gradual is not None
        assert hass.states.get(gradual.entity_id).state == gradual_state


async def test_h607c_registered_gradual_tracks_identity_and_release_reconnect(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    coordinator._present = coordinator.is_on = True
    coordinator._h607c_advertised_pacts = {(3, 1)}
    coordinator._resolve_h607c_pact()
    entry = await _register_h607c_entities(hass, coordinator)
    registry = er.async_get(hass)
    assert not any(
        item.unique_id.endswith("_gradual") for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    )

    coordinator._h607c_advertised_pacts = {(1, 1)}
    coordinator._resolve_h607c_pact()
    await hass.async_block_till_done()
    gradual = next(
        item
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if item.unique_id.endswith("_gradual")
    )
    assert hass.states.get(gradual.entity_id).state == "unknown"

    coordinator._h607c_advertised_pacts = {(1, 1), (2, 1)}
    coordinator._resolve_h607c_pact()
    await hass.async_block_till_done()
    assert hass.states.get(gradual.entity_id).state == "unavailable"

    coordinator._h607c_advertised_pacts.clear()
    coordinator._h607c_marker_seen = True
    coordinator._h607c_marker_pact = (1, 1)
    coordinator._resolve_h607c_pact()
    first = client()
    coordinator._client = first
    coordinator._clear_client_state(first)
    await hass.async_block_till_done()
    assert coordinator.h607c_pact_readiness == "stale"
    assert hass.states.get(gradual.entity_id).state == "unknown"

    coordinator._client = client()
    coordinator._h607c_marker_pact = (1, 1)
    coordinator._resolve_h607c_pact(preserve_state=True)
    await hass.async_block_till_done()
    assert coordinator.h607c_pact_readiness == "ready"
    assert hass.states.get(gradual.entity_id).state == "unknown"


async def test_h607c_registered_light_exposes_colour_uncertainty_and_assumed_retry(hass, h607c_light):
    coordinator, device, light = h607c_light
    coordinator.is_on = True
    entry = await _register_h607c_entities(hass, coordinator)
    registered = next(
        item for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if item.domain == "light"
    )
    device.write_gatt_char.side_effect = ValueError("write interrupted")
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(rgb_color=(12, 34, 56))
    await hass.async_block_till_done()
    state = hass.states.get(registered.entity_id)
    assert state.state == "on" and state.attributes["color_mode"] == "unknown"
    assert state.attributes["unconfirmed_state_fields"] == ["color", "color_mode"]
    assert state.attributes["rgb_color"] is None

    device.write_gatt_char.side_effect = None
    await light.async_turn_on(rgb_color=(40, 50, 60))
    await hass.async_block_till_done()
    state = hass.states.get(registered.entity_id)
    assert state.attributes["color_mode"] == "rgb" and state.attributes["rgb_color"] == (40, 50, 60)
    assert state.attributes["unconfirmed_state_fields"] == ["color"] and state.attributes["assumed_state"] is True
    assert light.extra_restore_state_data is None


async def test_h607c_marker_requalification_preserves_release_state_without_fresh_observations(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    first = client(bytes.fromhex("020000000101"))
    second = client(bytes.fromhex("020000000101"))
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(side_effect=[first, second]))
    monkeypatch.setattr(coordinator, "_start_keep_alive", lambda: None)
    await coordinator._ensure_connected()
    coordinator.brightness_pct = 37
    coordinator.color_temp_kelvin = 3200
    coordinator.boolean_control_state["gradual"] = True
    revisions = dict(coordinator._field_revisions)
    coordinator._intentional_disconnect_client = first
    coordinator._clear_client_state(first)
    coordinator._intentional_disconnect_client = None
    assert coordinator.boolean_control_state["gradual"] is True
    assert not coordinator._authorization_profile().supports_rgb
    await coordinator._ensure_connected()
    assert coordinator.profile.supports_rgb
    assert coordinator.brightness_pct == 37 and coordinator.color_temp_kelvin == 3200
    assert coordinator.boolean_control_state["gradual"] is True
    assert coordinator._field_revisions == revisions
    coordinator._clear_client_state(second)


async def test_h607c_unsupported_identity_invalidates_state_preserved_during_release(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    coordinator._h607c_marker_seen = True
    coordinator._h607c_marker_pact = (1, 1)
    coordinator._resolve_h607c_pact()
    coordinator._notify_callback(None, bytearray(_packet(0xAA, 4, [37])))
    coordinator.color_temp_kelvin = 3200
    coordinator.boolean_control_state["gradual"] = True
    coordinator.power_on_behaviour, coordinator.power_on_open_flag = "on", 1
    device = client()
    coordinator._client = coordinator._intentional_disconnect_client = device
    coordinator._clear_client_state(device)
    coordinator._intentional_disconnect_client = None
    assert coordinator.h607c_pact_readiness == "stale"
    assert coordinator.boolean_control_state["gradual"] and coordinator.color_temp_kelvin == 3200

    coordinator._h607c_advertised_pacts = {(3, 1)}
    coordinator._resolve_h607c_pact()
    assert coordinator.h607c_pact_readiness == "unsupported"
    assert coordinator.brightness_pct == 37
    assert coordinator.color_temp_kelvin is None and not coordinator.boolean_control_state
    assert coordinator.power_on_behaviour is None and coordinator.power_on_open_flag is None


def v1_reply(opcode=1, key=KEY):
    body = bytes((0xE7, opcode)) + key + b"\0"
    return v1_transform(body + bytes((xor_checksum(body),)), KEY_COMMUNICATION, encrypt=True)


def v2_reply(iv_key=IV):
    nonce = bytes(range(12))
    header = b"\xe7\x11\0" + nonce
    return header + AESGCM(KEY_HANDSHAKE).encrypt(nonce, iv_key + b"H6099" + bytes.fromhex("112233445566"), header)


def client(marker=None, *, mtu=100):
    return SimpleNamespace(
        services=[SimpleNamespace(characteristics=[SimpleNamespace(uuid=ENCRYPTION_UUID)])]
        if marker is not None
        else [],
        read_gatt_char=AsyncMock(return_value=marker),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        disconnect=AsyncMock(),
        mtu_size=mtu,
        is_connected=True,
    )


async def negotiate(version=1, *, confirm=True):
    session = GoveeEncryptionSession()
    device = client(bytes((1, version)))
    await session.async_select(device, advertised=False)

    async def write(_uuid, frame, **_kwargs):
        if version == 1:
            opcode = parse_v1_handshake(frame).opcode
            session.decode(v1_reply(opcode if confirm else 1))
        else:
            session.decode(v2_reply())

    device.write_gatt_char.side_effect = write
    await session.async_negotiate(device)
    return session, device


@pytest.mark.parametrize(
    ("version", "failure"),
    [
        (0, "marker"),
        (0, "subscription_reset"),
        (1, "marker"),
        (1, "subscription"),
        (2, "subscription"),
        (1, "silence"),
        (2, "silence"),
        (1, "programming"),
        (1, "ambient_programming"),
        (2, "invalid_handshake"),
    ],
)
async def test_background_refresh_classifies_real_failure_origins(
    hass, monkeypatch, virtual_clock, caplog, version, failure
):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator._first_refresh_done = coordinator._present = coordinator._state_read_available = True
    coordinator.is_on, coordinator.brightness_pct = True, 42
    coordinator.async_set_updated_data(coordinator._state_snapshot())
    device = client(bytes((1, version)))

    def disconnect():
        device.is_connected = False
        coordinator._disconnected_callback(device)

    async def read(_uuid):
        disconnect()
        raise BleakError("private marker link failure")

    async def subscribe(_uuid, _receive):
        if failure == "subscription":
            raise BleakError("private subscription link failure")
        if failure == "subscription_reset":
            disconnect()

    async def write(_uuid, frame, **_kwargs):
        if failure == "silence":
            return
        reply = v1_reply(parse_v1_handshake(frame).opcode) if version == 1 else v2_reply()
        device.start_notify.await_args.args[1](
            None, bytearray(bytes(len(reply)) if failure == "invalid_handshake" else reply)
        )

    def transform(_packet):
        if failure == "ambient_programming":
            try:
                raise BleakError("earlier handled Bluetooth error")
            except BleakError:
                disconnect()
                raise ValueError("private programming failure") from None
        raise ValueError("private programming failure")

    device.disconnect.side_effect = disconnect
    device.start_notify.side_effect = subscribe
    device.write_gatt_char.side_effect = write
    if failure == "marker":
        coordinator._advertised_plaintext = version == 0
        device.read_gatt_char.side_effect = read
    if "programming" in failure:
        coordinator.profile = replace(coordinator.profile, outbound_transform=transform)
    establish = AsyncMock(return_value=device)
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", establish)
    component = EntityComponent(logging.getLogger(__name__), "light", hass)
    light = GoveeBLELight(coordinator)
    await component.async_add_entities([light])
    try:
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        operational = failure not in {"programming", "ambient_programming", "invalid_handshake"}
        assert coordinator.last_update_success is operational
        assert light.available is operational
        assert hass.states.get(light.entity_id).state == ("on" if operational else "unavailable")
        assert coordinator.data["is_on"] is True and coordinator.data["brightness_pct"] == 42
        assert not coordinator._state_read_available
        assert coordinator._client is None and coordinator._keep_alive_task is None
        assert not coordinator._encryption.ready and coordinator._encryption._key is None
        assert coordinator.control_write_attempts == 0
        establish.assert_awaited_once()
        device.disconnect.assert_awaited_once()
        if operational:
            assert not any(record.levelno >= logging.ERROR for record in caplog.records)
            coordinator._set_present(False)
            assert not light.available
            coordinator._async_on_advertisement(SimpleNamespace(manufacturer_data={}), None)
            await hass.async_block_till_done()
            assert light.available and hass.states.get(light.entity_id).state == "on"
        else:
            assert type(coordinator.last_exception) is GoveeCryptoError
            assert any("Unexpected error fetching" in record.getMessage() for record in caplog.records)
            assert "private" not in str(coordinator.last_exception)
    finally:
        await light.async_remove()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("workflow", ["command", "effect", "preview"])
@pytest.mark.parametrize("failure", ["subscription", "previously_encrypted_connection"])
async def test_transport_classification_does_not_add_foreground_attempts(hass, monkeypatch, workflow, failure):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    device = client(b"\x01\x01")
    if failure == "subscription":
        device.start_notify.side_effect = BleakError("private subscription failure")
        establish = AsyncMock(return_value=device)
    else:
        coordinator._encryption = GoveeEncryptionSession()
        await coordinator._encryption.async_select(device, advertised=False)
        establish = AsyncMock(side_effect=BleakError("private reconnection failure"))
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", establish)
    try:
        with pytest.raises(GoveeTransportError, match="encrypted_setup_failed"):
            if workflow == "command":
                await coordinator.send_command(build_power(True))
            elif workflow == "effect":
                await coordinator.async_write_effect_sequence((build_power(True),), intent=ControlIntent.USER)
            else:
                await coordinator.async_preview_preflight()
        establish.assert_awaited_once()
        device.write_gatt_char.assert_not_awaited()
        assert coordinator.control_write_attempts == 0 and not coordinator.packet_log
        assert coordinator._client is None and not coordinator._encryption.ready
        assert coordinator._encryption.required_version == 1
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("advertised", "marker", "version"),
    [
        (False, None, 0),
        (True, None, 1),
        (False, b"\x01\0", 0),
        (False, b"\x02\0\0\0\0\0", 0),
        (True, b"\x01\0", 1),
        (True, b"\x02\0\0\0\0\0", 1),
        (False, b"\x01\x01", 1),
        (True, b"\x01\x02", 2),
        (False, b"\x02\x02\0\x01\x02\x03", 2),
        (False, b"\x02\x01\0\x01\x02\x03", 1),
    ],
)
async def test_selection_without_probe(advertised, marker, version):
    session, device = GoveeEncryptionSession(), client(marker)
    await session.async_select(device, advertised=advertised)
    assert session.version == version
    device.write_gatt_char.assert_not_awaited()
    if marker is None:
        device.read_gatt_char.assert_not_awaited()
    if version == 0:
        assert session.ready and session.last_result == "plaintext"
        await session.async_negotiate(device)
        assert session.encode(build_power(True)) == build_power(True)
        assert session.decode(build_power(True)) == build_power(True)
        device.write_gatt_char.assert_not_awaited()
    else:
        with pytest.raises(GoveeCryptoError):
            session.encode(build_power(True))


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("marker", [b"\x01\0", b"\x02\0\0\0\0\0"])
async def test_zero_marker_preserves_previous_encryption_requirement(version, marker):
    session = GoveeEncryptionSession()
    await session.async_select(client(bytes((1, version))), advertised=False)
    device = client(marker)
    await session.async_select(device, advertised=False)
    assert session.version == session.required_version == version
    assert not session.ready
    with pytest.raises(GoveeCryptoError, match="session_not_ready"):
        session.encode(build_power(True))
    device.write_gatt_char.assert_not_awaited()


UNRECOGNISED_MARKERS = [b"", b"\0", b"\x01", b"\x02\x02", b"\x02\0", b"\x03\x01", b"\x01\x03", "not bytes"]


@pytest.mark.parametrize("marker", UNRECOGNISED_MARKERS)
async def test_invalid_marker_never_becomes_plaintext(marker):
    session, device = GoveeEncryptionSession(), client(marker)
    with pytest.raises(GoveeCryptoError, match="selection_failed") as error:
        await session.async_select(device, advertised=False)
    assert type(error.value) is GoveeCryptoError
    device.services = []
    with pytest.raises(GoveeCryptoError):
        await session.async_select(device, advertised=False)
    with pytest.raises(GoveeCryptoError):
        session.encode(build_power(True))
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("marker", [*UNRECOGNISED_MARKERS, RuntimeError("secret address/key payload")])
async def test_plaintext_advertisement_allows_unrecognised_marker(marker):
    session, device = GoveeEncryptionSession(), client(b"\x01\x01")
    if isinstance(marker, Exception):
        device.read_gatt_char.side_effect = marker
    else:
        device.read_gatt_char.return_value = marker
    await session.async_select(device, advertised=False, plaintext_evidence=True)
    assert session.ready and session.version == 0
    assert session.last_result == "plaintext_unrecognised_marker"
    assert session.marker_hex == (marker[:32].hex() if isinstance(marker, bytes) else None)
    assert session.marker_error in {"GoveeCryptoError", "RuntimeError"}
    assert "secret" not in json.dumps(session.diagnostics())
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("marker", UNRECOGNISED_MARKERS)
async def test_plaintext_advertisement_never_overrides_encryption_evidence(marker):
    advertised = GoveeEncryptionSession()
    with pytest.raises(GoveeCryptoError, match="selection_failed"):
        await advertised.async_select(client(marker), advertised=True, plaintext_evidence=True)
    assert not advertised.ready

    previously_encrypted = GoveeEncryptionSession()
    await previously_encrypted.async_select(client(b"\x01\x01"), advertised=False)
    with pytest.raises(GoveeCryptoError, match="selection_failed"):
        await previously_encrypted.async_select(client(marker), advertised=False, plaintext_evidence=True)
    assert not previously_encrypted.ready


async def test_profile_plaintext_marker_recovers_without_advertisement():
    session, device = GoveeEncryptionSession(), client(b"\0")
    with pytest.raises(GoveeCryptoError):
        await session.async_select(device, advertised=False)
    await session.async_select(device, advertised=False, allows_legacy_plaintext_marker=True)
    assert session.ready and session.version == 0
    assert session.last_result == "plaintext_profile_marker"
    await session.async_negotiate(device)
    assert session.encode(build_power(True)) == build_power(True)
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("version", [0, 1, 2])
async def test_profile_marker_never_overrides_encryption(version):
    session = GoveeEncryptionSession()
    if version:
        await session.async_select(client(bytes((1, version))), advertised=False)
    with pytest.raises(GoveeCryptoError):
        await session.async_select(client(b"\0"), advertised=not version, allows_legacy_plaintext_marker=True)
    assert not session.ready and session.required_version == (version or 1)


@pytest.mark.parametrize("marker", [b"", b"\0\0", b"\0\1", b"\1", b"\2", "not bytes", RuntimeError("read failed")])
async def test_profile_marker_requires_exact_successful_read(marker):
    device = client(b"\0")
    if isinstance(marker, Exception):
        device.read_gatt_char.side_effect = marker
    else:
        device.read_gatt_char.return_value = marker
    session = GoveeEncryptionSession()
    with pytest.raises(GoveeCryptoError):
        await session.async_select(device, advertised=False, allows_legacy_plaintext_marker=True)
    assert not session.ready
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("reset", [False, True])
async def test_profile_marker_does_not_confirm_a_retired_subscription(reset):
    session, device = GoveeEncryptionSession(), client(b"\0")

    async def read(_uuid):
        if reset:
            session.reset()
        else:
            device.is_connected = False
        return b"\0"

    device.read_gatt_char.side_effect = read
    with pytest.raises(GoveeCryptoError) as error:
        await session.async_select(device, advertised=False, allows_legacy_plaintext_marker=True)
    assert type(error.value) is GoveeCryptoError
    assert not session.ready


@pytest.mark.parametrize("error_type", [BleakError, RuntimeError])
@pytest.mark.parametrize("plaintext_evidence", [False, True])
async def test_read_failure_has_no_raw_error_or_disconnected_fallback(error_type, plaintext_evidence):
    session, device = GoveeEncryptionSession(), client(b"\x01\x02")

    async def read(_uuid):
        device.is_connected = False
        try:
            raise BleakError("earlier handled Bluetooth error")
        except BleakError:
            raise error_type("secret address/key payload") from None

    device.read_gatt_char.side_effect = read
    with pytest.raises(GoveeCryptoError) as err:
        await session.async_select(device, advertised=False, plaintext_evidence=plaintext_evidence)
    assert type(err.value) is (GoveeTransportError if error_type is BleakError else GoveeCryptoError)
    assert err.value.__suppress_context__
    assert "secret" not in str(err.value)
    assert "secret" not in json.dumps(session.diagnostics())
    assert not session.ready
    device.write_gatt_char.assert_not_awaited()
    device.is_connected = True
    device.services = []
    with pytest.raises(GoveeCryptoError, match="encryption_selection_failed") as failed:
        await session.async_select(device, advertised=False)
    assert type(failed.value) is GoveeCryptoError
    assert not session.ready


def test_advertisement_and_omissions(hass):
    positive = {0x8843: bytes.fromhex("ec010203")}
    assert parse_govee_advertisement(positive).supports_encryption
    assert parse_govee_advertisement({0x8843: b"\xec"}) is None
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={0x8801: bytes.fromhex("ec000101")}))
    assert coordinator._advertised_plaintext and not coordinator._advertised_encryption
    for data in (positive, {}, {0x8803: bytes.fromhex("ec010203")}):
        coordinator._note_advertisement(SimpleNamespace(manufacturer_data=data))
        assert coordinator._advertised_encryption


@pytest.mark.parametrize(
    ("company_id", "pacts", "encrypted", "plaintext", "invalid_version"),
    [
        (0x8800, frozenset(), False, False, True),
        (0x8840, frozenset(), True, False, True),
        (0x8801, frozenset({(1, 1)}), False, True, False),
        (0x8843, frozenset({(1, 1)}), True, False, False),
    ],
)
def test_advertisement_version_qualifies_identity_separately_from_encryption(
    company_id, pacts, encrypted, plaintext, invalid_version
):
    parsed = parse_govee_advertisement({company_id: bytes.fromhex("ec00010100")})
    assert parsed is not None
    assert parsed.pacts == pacts
    assert parsed.supports_encryption is encrypted
    assert parsed.supports_plaintext is plaintext
    assert parsed.invalid_version_seen is invalid_version


@pytest.mark.parametrize("invalid_first", [False, True])
async def test_h607c_invalid_advertisement_cannot_mask_valid_identity_or_encryption(hass, invalid_first):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    records = [(0x8840, bytes.fromhex("ec00030100")), (0x8801, bytes.fromhex("ec00010100"))]
    if not invalid_first:
        records.reverse()
    info = SimpleNamespace(name="Govee_H607C", source="scanner", time=time.monotonic(), manufacturer_data=dict(records))
    coordinator._note_advertisement(info)
    coordinator._prune_h607c_advertisements()

    assert (coordinator.pact_type, coordinator.pact_code) == (1, 1)
    assert coordinator.h607c_pact_readiness == "ready"
    assert coordinator._advertised_encryption and coordinator._advertised_plaintext
    assert coordinator._h607c_invalid_pact_version_seen


async def test_h607c_newer_invalid_version_revokes_old_scanner_pact(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    now = time.monotonic()
    valid = SimpleNamespace(
        name="Govee_H607C",
        source="scanner",
        time=now,
        manufacturer_data={0x8843: bytes.fromhex("ec00010100")},
    )
    invalid = SimpleNamespace(
        name=valid.name,
        source=valid.source,
        time=now + 0.001,
        manufacturer_data={0x8840: bytes.fromhex("ec00010100")},
    )
    coordinator._note_advertisement(valid)
    coordinator._prune_h607c_advertisements()
    assert coordinator.h607c_pact_readiness == "ready"

    coordinator._note_advertisement(invalid)
    coordinator._note_advertisement(valid, cached=True)
    coordinator._prune_h607c_advertisements()
    assert coordinator.h607c_pact_readiness == "missing"
    assert not coordinator._authorization_profile().supports_rgb
    assert coordinator._advertised_encryption and not coordinator._advertised_plaintext


async def test_h607c_conflicting_valid_pacts_in_one_advertisement_fail_closed(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H607C", configuration_url=None)
    info = SimpleNamespace(
        name="Govee_H607C",
        source="scanner",
        time=time.monotonic(),
        manufacturer_data={0x8801: bytes.fromhex("ec00010100"), 0x8802: bytes.fromhex("ec00020100")},
    )
    coordinator._note_advertisement(info)
    coordinator._prune_h607c_advertisements()
    assert coordinator.h607c_pact_readiness == "conflicting"
    assert not coordinator._authorization_profile().supports_rgb


def test_h6097_owner_advertisement_requires_encrypted_negotiation(hass):
    # Non-identifying manufacturer record supplied by an owner.
    data = {0x8843: bytes.fromhex("ec00020100")}
    parsed = parse_govee_advertisement(data)
    assert parsed is not None and parsed.supports_encryption
    assert parsed.pacts == frozenset({(2, 1)})
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6097", configuration_url=None)
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data=data))
    assert coordinator._advertised_encryption and not coordinator._advertised_plaintext
    assert coordinator.profile.supports_rgb and coordinator.profile.music_modes


def test_h6097_runtime_profile_tracks_pact_without_version_queries(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6097", configuration_url=None)
    assert not coordinator.profile.supports_rgb and not coordinator.profile.supports_power_on_behaviour
    generation = coordinator._profile_generation
    for payload, supported in (("ec00020100", True), ("ec000a0300", False), ("ec00010100", True)):
        coordinator._note_advertisement(SimpleNamespace(manufacturer_data={0x8843: bytes.fromhex(payload)}))
        assert coordinator.profile.supports_rgb is supported
        assert coordinator.profile.supports_power_on_behaviour is supported
        assert coordinator._profile_generation > generation
        generation = coordinator._profile_generation


@pytest.mark.parametrize("model", ["H6076", "H6181"])
async def test_coordinator_uses_qualified_plaintext_marker_policy(hass, model):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    coordinator.profile = replace(
        coordinator.profile,
        read_domains=frozenset(),
        setup_required_read_domains=frozenset(),
    )
    device = client(b"\0" if model == "H6181" else b"\x01\x01")
    if model == "H6076":
        device.read_gatt_char.side_effect = BleakError("Not permitted")
        coordinator._note_advertisement(SimpleNamespace(manufacturer_data={0x8801: bytes.fromhex("ec000101")}))
    with patch(f"{M}.async_establish_ble_connection", return_value=device):
        await coordinator.send_command(build_power(True, model))
    assert coordinator._encryption.last_result == (
        "plaintext_profile_marker" if model == "H6181" else "plaintext_unrecognised_marker"
    )
    device.write_gatt_char.assert_awaited_with(WRITE_UUID, build_power(True, model), response=False)


async def test_h6181_marker_pact_is_reconciled_again_on_reconnect(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    device = client(bytes((2, 0, 0, 0, 10, 2)))
    monkeypatch.setattr(coordinator, "_send_identity_queries", AsyncMock())
    monkeypatch.setattr(coordinator, "_wait_for_revisions", AsyncMock(return_value=False))
    monkeypatch.setattr(coordinator, "_start_keep_alive", lambda: None)
    monkeypatch.setattr(coordinator, "_refresh_h607c_advertisements", lambda: None)
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(return_value=device))
    await coordinator.send_command(build_power(True, "H6181"))
    assert (coordinator.pact_type, coordinator.pact_code) == (10, 2)
    assert coordinator.profile.brightness_wire_range is None
    assert coordinator.profile.diy_upload_transport == "a3"
    coordinator._clear_client_state(device)
    assert coordinator._h607c_marker_pact is None
    assert (coordinator.pact_type, coordinator.pact_code) == (10, 2)
    device.read_gatt_char.return_value = b"\0"
    await coordinator.send_command(build_power(True, "H6181"))
    assert (coordinator.pact_type, coordinator.pact_code) == (None, None)
    assert coordinator.profile.brightness_wire_range == (20, 254)
    assert coordinator._encryption.last_result == "plaintext_profile_marker"
    coordinator._clear_client_state(device)


@pytest.mark.parametrize("fresh", [False, True])
async def test_h6181_marker_only_conflicts_with_current_subscription_advertisements(hass, fresh):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6181", configuration_url=None)
    coordinator._client = client()
    now = time.monotonic()
    coordinator._notify_started_monotonic = now
    coordinator._h607c_marker_pact = (10, 2)
    coordinator._note_advertisement(
        SimpleNamespace(
            name="Govee_H6181",
            source="scanner-a",
            time=now + 1 if fresh else now - 1,
            manufacturer_data={0x8801: bytes.fromhex("ec000101")},
        )
    )
    coordinator._prune_h607c_advertisements()
    assert coordinator._h607c_pact_conflict is fresh
    if fresh:
        with pytest.raises(ValueError):
            coordinator._validate_authorized_packet(build_power(True, "H6181"))
    else:
        assert (coordinator.pact_type, coordinator.pact_code) == (10, 2)
        coordinator._validate_authorized_packet(build_power(True, "H6181"))
    coordinator._clear_client_state(coordinator._client)


async def test_v1_confirmation_is_mandatory_and_opcode_specific(monkeypatch):
    assert session_module.HANDSHAKE_TIMEOUT == 6
    monkeypatch.setattr(session_module, "HANDSHAKE_TIMEOUT", 0.01)
    with pytest.raises(GoveeCryptoError, match="timeout"):
        await negotiate(confirm=False)
    session, device = await negotiate()
    assert session.active
    assert [parse_v1_handshake(c.args[1]).opcode for c in device.write_gatt_char.await_args_list] == [1, 2]
    packet = build_power(True)
    assert v1_transform(session.encode(packet), KEY, encrypt=False) == packet
    session.reset()
    assert not session.active and session._key is None
    with pytest.raises(GoveeCryptoError):
        session.encode(packet)
    await session.async_select(client(), advertised=False)
    assert session.version == 1 and not session.ready


@pytest.mark.parametrize("reply", [b"bad", bytes(20), v1_reply()[:-1]])
async def test_invalid_key_reply_fails_closed(reply):
    session, device = GoveeEncryptionSession(), client(b"\x01\x01")
    await session.async_select(device, advertised=False)
    device.write_gatt_char.side_effect = lambda *_args, **_kw: session.decode(reply)
    with pytest.raises(GoveeCryptoError) as error:
        await session.async_negotiate(device)
    assert type(error.value) is GoveeCryptoError
    assert not session.ready and session._key is None
    assert device.write_gatt_char.await_count == 1


def test_known_v2_request_and_key_vector():
    assert (
        build_v2_handshake(bytes.fromhex("fe332c0eca3eb701"), nonce=bytes.fromhex("38fab547fcce6a692dd093c7")).hex()
        == "e7110138fab547fcce6a692dd093c710712d825424fe256368b02083d7b367f36b8595c12c60cd92"
    )
    with pytest.raises(GoveeCryptoError):
        build_v2_handshake(IV, tag_len=12)
    assert parse_v2_handshake(v2_reply())[0] == IV


async def test_v2_authentication_replay_and_counter_exhaustion():
    session, _device = await negotiate(2)
    _, key = parse_v2_handshake(v2_reply())
    frame = seal(build_power_query(), IV, key, 1)
    bad = bytearray(frame)
    bad[3] = 50
    assert session.decode(bytes(bad)) is None
    assert session._received_counter == 0
    assert session.decode(frame) == build_power_query()
    assert session.decode(frame) is None
    assert session.decode(seal(build_power_query(), IV, key, 3)) == build_power_query()
    assert session.decode(seal(build_power_query(), IV, key, 2)) is None
    assert session.decode(build_power_query()) is None
    session._counter = 0xFFFFFFFF
    assert unseal(session.encode(build_power(True)), session._client_iv, key)[0] == 0xFFFFFFFF
    with pytest.raises(GoveeCryptoError, match="exhausted"):
        session.encode(build_power(True))


@pytest.mark.parametrize("mtu", [0, 23, 51, 52, None])
async def test_v2_short_or_unknown_mtu_fails_before_writing(mtu):
    session, device = GoveeEncryptionSession(), client(b"\x01\x02", mtu=mtu)
    await session.async_select(device, advertised=False)
    with pytest.raises(GoveeCryptoError) as error:
        await session.async_negotiate(device)
    assert type(error.value) is GoveeCryptoError
    assert not session.ready
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("phase", ["select", "key", "confirm", "write"])
async def test_coordinator_cancellation_resets_session(hass, phase):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6076", configuration_url=None)
    device, entered = client(b"\x01\x01"), asyncio.Event()

    async def block(*_args, **_kwargs):
        entered.set()
        await asyncio.Event().wait()

    async def write(_uuid, frame, **_kwargs):
        count = device.write_gatt_char.await_count
        if (phase == "key" and count == 1) or (phase == "confirm" and count == 2) or count == 3:
            await block()
        else:
            coordinator._notify_callback(None, bytearray(v1_reply(count)))

    device.write_gatt_char.side_effect = write
    if phase == "select":
        device.read_gatt_char.side_effect = block
    with patch(f"{M}.async_establish_ble_connection", return_value=device):
        task = asyncio.create_task(coordinator.send_command(build_power(True, "H6076")))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert coordinator._client is None
    assert not coordinator._connection_initializing
    assert not coordinator._encryption.ready
    assert coordinator._encryption._key is None
    assert coordinator._encryption._handshake is None
    assert coordinator.packet_log == []
    device.disconnect.assert_awaited_once()


@pytest.mark.parametrize("version", [1, 2])
async def test_encrypted_write_only_reconnect_transforms_and_stale_notifications(hass, version):
    # An identity-qualified model would re-resolve this substituted profile on reconnect.
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    packet = build_power(True, "H617A")
    logical = []
    coordinator.profile = replace(
        coordinator.profile,
        read_domains=frozenset(),
        setup_required_read_domains=frozenset(),
        outbound_transform=lambda p: logical.append(p) or b"\xfe" + p,
    )
    callbacks, sessions = [], []
    for connection in range(2):
        device = client(bytes((1, version)))
        phase = 0
        client_iv = None

        async def write(_uuid, frame, device=device, **_kwargs):
            nonlocal phase, client_iv
            phase += 1
            if version == 1 and phase <= 2:
                device.start_notify.call_args.args[1](None, bytearray(v1_reply(phase)))
            elif version == 2 and phase == 1:
                parsed = parse_wire("V2Request", frame)
                client_iv = AESGCM(KEY_HANDSHAKE).decrypt(parsed.nonce, parsed.sealed, frame[:16])
                device.start_notify.call_args.args[1](None, bytearray(v2_reply()))
            else:
                assert coordinator.is_on
                plain = (
                    v1_transform(frame, KEY, encrypt=False)
                    if version == 1
                    else unseal(frame, client_iv, parse_v2_handshake(v2_reply())[1])[1]
                )
                assert plain == b"\xfe" + packet
                assert frame != plain and frame != packet

        device.write_gatt_char.side_effect = write
        with patch(f"{M}.async_establish_ble_connection", return_value=device):
            await coordinator.send_command(packet, state_values={"is_on": True})
            assert await coordinator._ensure_connected() is device
        device.start_notify.assert_awaited_once()
        assert device.start_notify.call_args.args[0] == READ_UUID
        callbacks.append(device.start_notify.call_args.args[1])
        sessions.append(coordinator._encryption._client_iv)
        if connection:
            baseline = coordinator._last_rx_monotonic
            callbacks[0](None, bytearray(v1_reply()))
            assert coordinator._last_rx_monotonic == baseline
        assert all(c.args[0] == WRITE_UUID for c in device.write_gatt_char.await_args_list)
        await coordinator.disconnect()
        assert coordinator._encryption._key is None
    assert logical == [packet, packet]
    if version == 2:
        assert sessions[0] != sessions[1]
    assert len(coordinator.packet_log) == 2  # No handshake/key packets in diagnostics.


async def test_encryption_failure_and_guard_precede_optimistic_assignment(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    session, device = await negotiate(2)
    coordinator._client, coordinator._encryption = device, session
    device.write_gatt_char.reset_mock()
    packet = build_power(True)
    session._counter = 0x100000000
    with pytest.raises(GoveeCryptoError):
        await coordinator._async_write_packet(device, packet, arm_expected=True, state_values={"is_on": True})
    assert not coordinator.is_on and not coordinator._expected_state
    session._counter = 2

    def guard():
        raise ValueError("guard")

    with pytest.raises(ValueError, match="guard"):
        await coordinator._async_write_packet(device, packet, before_write=guard, state_values={"is_on": True})
    assert not coordinator.is_on
    device.write_gatt_char.assert_not_awaited()
    assert coordinator.control_write_attempts == 0


async def test_no_half_ready_fast_path(hass):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6076", configuration_url=None)
    coordinator._client = client()
    coordinator._connection_initializing = True
    with pytest.raises(GoveeCryptoError, match="setup_in_progress"):
        await coordinator._ensure_connected()


@pytest.mark.parametrize("workflow", ["effect", "preview"])
async def test_slow_connection_and_encrypted_setup_fit_operation_budget(hass, virtual_clock, workflow):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    coordinator.profile = replace(
        coordinator.profile, read_domains=frozenset(), setup_required_read_domains=frozenset()
    )
    device = client(b"\x01\x01")
    phase = 0

    async def connect(*_args, **_kwargs):
        await asyncio.sleep(19)
        return device

    async def write(_uuid, frame, **_kwargs):
        nonlocal phase
        phase += 1
        if phase <= 2:
            await asyncio.sleep(5)
            device.start_notify.await_args.args[1](None, bytearray(v1_reply(phase)))
        else:
            assert v1_transform(frame, KEY, encrypt=False) == build_power(True)

    device.write_gatt_char.side_effect = write
    try:
        with patch(f"{M}.async_establish_ble_connection", side_effect=connect) as establish:
            if workflow == "effect":
                await coordinator.async_write_effect_sequence((build_power(True),), intent=ControlIntent.USER)
            else:
                await coordinator.async_preview_preflight()
                await coordinator.async_preview_write(build_power(True))
        establish.assert_awaited_once()
        assert coordinator._encryption.ready and coordinator.is_on
        assert phase == 3
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("pending", [False, True])
async def test_disconnect_during_handshake_cannot_install_keys(version, pending):
    session, device = GoveeEncryptionSession(), client(bytes((1, version)))
    await session.async_select(device, advertised=False)

    async def write(_uuid, frame, **_kwargs):
        if not pending:
            session.decode(v1_reply(parse_v1_handshake(frame).opcode) if version == 1 else v2_reply())
        session.reset()  # A disconnect can land after the future resolves but before its waiter resumes.

    device.write_gatt_char.side_effect = write
    with pytest.raises(GoveeTransportError, match="negotiation_failed"):
        await session.async_negotiate(device)
    assert not session.ready and session._key is None
    assert device.write_gatt_char.await_count == 1


@pytest.mark.parametrize("version", [1, 2])
async def test_encrypted_notifications_preserve_fresh_readback(hass, version):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    session, device = await negotiate(version)
    coordinator._client, coordinator._encryption = device, session
    response_body = b"\xaa\x01\x01" + bytes(16)
    response = response_body + bytes((xor_checksum(response_body),))
    encrypted = (
        v1_transform(response, KEY, encrypt=True)
        if version == 1
        else seal(response, IV, parse_v2_handshake(v2_reply())[1], 1)
    )

    async def write(*_args, **_kwargs):
        coordinator._notify_callback(None, bytearray(encrypted))

    device.write_gatt_char.side_effect = write
    await coordinator._async_write_packet(device, build_power_query(), state_values={"is_on": False})
    assert coordinator.is_on and coordinator._field_revisions["is_on"] == 1
    baseline = coordinator._last_rx_monotonic
    coordinator._notify_callback(None, bytearray(build_power_query()))
    assert coordinator._last_rx_monotonic == baseline
    assert coordinator._field_revisions["is_on"] == 1
    assert not coordinator._expected_state


@pytest.mark.parametrize(
    "error, expected",
    [(RuntimeError, GoveeCryptoError), (BleakError, BleakError), (GoveeTransportError, GoveeTransportError)],
)
async def test_transport_write_failure_hides_backend_exception(hass, error, expected):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    session, device = await negotiate()
    coordinator._client, coordinator._encryption = device, session
    device.write_gatt_char.side_effect = error("private address and secret frame")
    with pytest.raises(expected, match="encrypted_write_failed") as err:
        await coordinator._async_write_packet(device, build_power(True))
    assert err.value.__suppress_context__
    assert "private" not in str(err.value)
    assert coordinator.packet_log == []
    assert coordinator._client is None and not session.ready


async def test_v2_fragments_and_oversized_writes_are_rejected():
    session, device = await negotiate(2)
    assert session.decode(b"\xe7\x1a" + bytes(18)) is None
    assert session.decode(b"\xff" + bytes(19)) is None
    with pytest.raises(GoveeCryptoError, match="fragmentation_unsupported"):
        session.encode(bytes(device.mtu_size))
    assert session._counter == 2


@pytest.mark.parametrize("failure", ["silence", "duplicate", "subscription"])
async def test_failed_negotiation_never_sends_control_plaintext(hass, monkeypatch, failure):
    monkeypatch.setattr(session_module, "HANDSHAKE_TIMEOUT", 0.01)
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6076", configuration_url=None)
    device = client()
    coordinator._note_advertisement(SimpleNamespace(manufacturer_data={0x8843: bytes.fromhex("ec010203")}))
    packet = build_power(True, "H6076")
    if failure == "subscription":
        device.start_notify.side_effect = RuntimeError("private subscription payload")
    elif failure == "duplicate":
        device.write_gatt_char.side_effect = lambda *_a, **_kw: coordinator._notify_callback(
            None, bytearray(v1_reply())
        )
    with patch(f"{M}.async_establish_ble_connection", return_value=device):
        with pytest.raises(GoveeCryptoError):
            await coordinator.send_command(packet, state_values={"is_on": True})
    assert not coordinator.is_on
    assert coordinator._client is None and not coordinator._encryption.ready
    assert all(c.args[1] != packet for c in device.write_gatt_char.await_args_list)
    assert coordinator.packet_log == [] and coordinator.control_write_attempts == 0
    device.read_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("negotiated_mtu", [23, 52, 53, 100])
async def test_ha_bluez_cached_mtu_is_acquired_from_dbus(negotiated_mtu):
    session = GoveeEncryptionSession()
    await session.async_select(client(b"\x01\x02"), advertised=False)
    backend = BleakClientBlueZDBus("11:22:33:44:55:66", bluez={}, timeout=10)
    backend._is_connected = True
    backend.services = SimpleNamespace(
        characteristics={
            1: SimpleNamespace(properties=["write-without-response"], obj=("/org/bluez/hci0/dev_test/service/char", {}))
        }
    )
    # Exercise the installed native _acquire_mtu and HA's inherited mtu_size
    # property, replacing only D-Bus I/O. AcquireWrite returns a closable fd.
    read_fd, write_fd = os.pipe()
    backend._bus = SimpleNamespace(
        call=AsyncMock(
            return_value=SimpleNamespace(
                message_type=MessageType.METHOD_RETURN, unix_fds=[read_fd], body=[0, negotiated_mtu]
            )
        )
    )
    device = object.__new__(HaBleakClientWrapper)
    device._backend = backend
    device.write_gatt_char = AsyncMock(side_effect=lambda *_a, **_kw: session.decode(v2_reply()))
    try:
        with pytest.warns(UserWarning, match="default MTU"):
            assert device.mtu_size == 23
        if negotiated_mtu < 53:
            with pytest.raises(GoveeCryptoError):
                await session.async_negotiate(device)
            device.write_gatt_char.assert_not_awaited()
        else:
            await session.async_negotiate(device)
            assert session.ready and session._mtu == negotiated_mtu
            session.encode(bytes(negotiated_mtu - 23))
            with pytest.raises(GoveeCryptoError, match="fragmentation_unsupported"):
                session.encode(bytes(negotiated_mtu - 22))
        assert device.mtu_size == negotiated_mtu
        backend._bus.call.assert_awaited_once()
        assert backend._bus.call.call_args.args[0].member == "AcquireWrite"
        with pytest.raises(OSError):
            os.fstat(read_fd)  # Bleak closed its acquired descriptor.
    finally:
        os.close(write_fd)


@pytest.mark.parametrize("failure", ["error", "cancel", "disconnect", "timeout"])
async def test_mtu_acquisition_failure_cannot_send_handshake(monkeypatch, failure):
    session, device = GoveeEncryptionSession(), client(b"\x01\x02", mtu=23)
    await session.async_select(device, advertised=False)
    entered = asyncio.Event()

    async def acquire():
        entered.set()
        if failure == "error":
            raise BleakError("private MTU error")
        if failure == "disconnect":
            session.reset()
            device.mtu_size = 100
            return
        await asyncio.Event().wait()

    device._backend = SimpleNamespace(_acquire_mtu=acquire)
    monkeypatch.setattr(session_module, "HANDSHAKE_TIMEOUT", 0.01)
    task = asyncio.create_task(session.async_negotiate(device))
    await entered.wait()
    if failure == "cancel":
        task.cancel()
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else GoveeTransportError):
        await task
    assert not session.ready and session._key is None
    assert "private" not in json.dumps(session.diagnostics())
    device.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("multipart", [False, True])
async def test_encrypted_write_retries_reconnect_with_fresh_session(hass, version, multipart):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    transformed = []
    coordinator.profile = replace(
        coordinator.profile,
        read_domains=frozenset(),
        setup_required_read_domains=frozenset(),
        outbound_transform=lambda p: transformed.append(p) or b"\xfe" + p,
    )
    packets = fragment_a3(3, bytes(range(40))) if multipart else [build_power(True)]
    devices, attempts, host_ivs, session_keys = [], [], [], []

    async def connect(*_args, **_kwargs):
        index = len(devices)
        device = client(bytes((1, version)))
        devices.append(device)
        attempts.append([])
        key = bytes((index + 1,)) * 16
        phase, host_iv = 0, None
        reply = v2_reply(bytes((index + 1,)) * 8)
        device_key = parse_v2_handshake(reply)[1]

        async def write(_uuid, frame, **_kw):
            nonlocal phase, host_iv
            phase += 1
            notify = device.start_notify.call_args.args[1]
            if version == 1 and phase <= 2:
                assert parse_v1_handshake(frame).opcode == phase
                notify(None, bytearray(v1_reply(phase, key)))
                if phase == 2:
                    session_keys.append(coordinator._encryption._key)
                return
            if version == 2 and phase == 1:
                parsed = parse_wire("V2Request", frame)
                host_iv = AESGCM(KEY_HANDSHAKE).decrypt(parsed.nonce, parsed.sealed, frame[:16])
                host_ivs.append(host_iv)
                notify(None, bytearray(reply))
                return
            if version == 1:
                assert coordinator._encryption._key == key
                plain = v1_transform(frame, key, encrypt=False)
            else:
                counter, plain = unseal(frame, host_iv, device_key)
                assert counter == 2 + len(attempts[index])
            assert frame not in packets and frame != plain
            attempts[index].append(plain)
            if index == 0 and len(attempts[index]) == (2 if multipart else 1):
                raise BleakError("private transient write failure")

        device.write_gatt_char.side_effect = write
        return device

    with patch(f"{M}.async_establish_ble_connection", side_effect=connect) as establish:
        if multipart:
            await coordinator.async_write_effect_sequence(packets, intent=ControlIntent.USER)
        else:
            await coordinator.send_command(packets[0])
    assert establish.await_count == 2
    assert attempts == [[b"\xfe" + p for p in packets[: 2 if multipart else 1]], [b"\xfe" + p for p in packets]]
    assert transformed == packets[: 2 if multipart else 1] + packets
    assert coordinator._encryption.active
    devices[0].disconnect.assert_awaited_once()
    for device in devices:
        device.start_notify.assert_awaited_once()
    if version == 2:
        assert host_ivs[0] != host_ivs[1]
    else:
        assert session_keys == [None, None]  # Keys aren't installed before confirmation returns.
    assert "private" not in json.dumps(coordinator._encryption.diagnostics())
    await coordinator.disconnect()


async def test_h6076_identity_and_music_travel_over_v1_and_the_companion_is_acknowledged(hass):
    # The reporter's lamp negotiated V1 and acknowledged each companion with an A3 reply.
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6076", configuration_url=None)
    coordinator.config_entry = MockConfigEntry(domain=DOMAIN, entry_id="test-entry")
    coordinator.config_entry.add_to_hass(hass)
    coordinator.pact_type, coordinator.pact_code = 1, 1
    coordinator._resolve_device_profile()
    assert coordinator.profile.music_modes == ("energetic", "rhythm", "bounce", "hopping", "beat", "spray")
    device, phase, plain_writes, wire_writes = client(bytes((1, 1))), 0, [], []

    def reply(payload):
        frame = payload.ljust(19, b"\0")
        frame += bytes((xor_checksum(frame),))
        device.start_notify.call_args.args[1](None, bytearray(v1_transform(frame, KEY, encrypt=True)))

    async def write(_uuid, frame, **_kwargs):
        nonlocal phase
        phase += 1
        if phase <= 2:
            device.start_notify.call_args.args[1](None, bytearray(v1_reply(phase)))
            return
        plain = v1_transform(frame, KEY, encrypt=False)
        wire_writes.append(frame)
        plain_writes.append(plain)
        if plain[:2] == b"\xaa\x07":
            reply(b"\xaa\x07\x03" + b"3.05.00\0")
        elif plain[:2] == b"\xaa\x06":
            reply(b"\xaa\x06" + b"1.04.05\0")
        elif plain[:2] == b"\xa3\xff":
            reply(b"\xa3\x41\x4d\x00")  # A late acknowledgement for a different mode must be ignored.
            assert not coordinator._upload_ack[-1].done()
            reply(b"\xa3\x41\x50\x00")

    device.write_gatt_char.side_effect = write
    with patch(f"{M}.async_establish_ble_connection", return_value=device):
        try:
            await coordinator._ensure_connected()
            assert coordinator.profile.music_modes
            expected = prepare_music_request(
                "H6076", "torch", coordinator.music_sensitivity, None, False, {}, profile=coordinator.profile
            )
            assert [packet[0] for packet in expected] == [0x33, 0xA3, 0xA3, 0x33]
            await coordinator.async_select_music_slug("torch")
        finally:
            await coordinator.disconnect()

    assert [plain[:2] for plain in plain_writes[:2]] == [b"\xaa\x07", b"\xaa\x06"]
    assert plain_writes[2:] == list(expected)
    assert all(frame != plain for frame, plain in zip(wire_writes, plain_writes, strict=True))
    assert coordinator.music_mode == "torch" and coordinator._encryption.version == 1
