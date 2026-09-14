"""Condition-bearing identity must come from the current connection, not cached display data."""

from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import current_entry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, ReadDomain, VideoFirmwareCondition
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_firmware_query,
    build_h6199_subordinate_query,
    build_hardware_query,
)
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum
from custom_components.ha_govee_led_ble.video_applicability import video_control_states
from tests.test_video_semantics import alternate

M = "custom_components.ha_govee_led_ble.coordinator"
IDENTITY = (
    ("fw_version", 0x06),
    ("hw_version", 0x07),
    ("subordinate_20_version", 0x20),
    ("subordinate_21_version", 0x21),
)


@pytest.fixture(params=IDENTITY, ids=[field for field, _ in IDENTITY])
def identity(hass, monkeypatch, request):
    field, opcode = request.param
    profile = replace(
        alternate(monkeypatch),
        read_domains=frozenset(
            {
                ReadDomain.POWER,
                ReadDomain.FIRMWARE,
                ReadDomain.HARDWARE,
                ReadDomain.SUBORDINATE_20,
                ReadDomain.SUBORDINATE_21,
            }
        ),
        video_firmware_conditions=(VideoFirmwareCondition("white_balance", field, "9.08.07"),),
    )
    monkeypatch.setitem(MODEL_PROFILES, "H7000", profile)
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    with current_entry.set(entry):
        coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H7000", configuration_url="test")
    for name, _ in IDENTITY:
        setattr(coordinator, name, "legacy display")
    query = (
        build_firmware_query("H7000")
        if opcode == 0x06
        else build_hardware_query("H7000")
        if opcode == 0x07
        else build_h6199_subordinate_query(opcode)
    )
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    return coordinator, field, opcode, query


def notify(coordinator, opcode, version):
    frame = bytearray(bytes((0xAA, opcode)) + (b"\x03" if opcode == 0x07 else b"") + version.encode("ascii"))
    frame.extend(bytes(19 - len(frame)))
    frame.append(xor_checksum(frame))
    coordinator._notify_callback(None, frame)


@pytest.mark.parametrize("stale_stream", [False, True])
async def test_reconnect_refreshes_only_condition_source(identity, monkeypatch, stale_stream):
    coordinator, field, opcode, query = identity
    notify(coordinator, opcode, "9.08.07")
    assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED
    old_client = MagicMock(is_connected=stale_stream, disconnect=AsyncMock())
    coordinator._client = old_client
    monkeypatch.setattr(coordinator, "_receive_is_stale", lambda: stale_stream)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    async def connect(*args, **kwargs):
        assert getattr(coordinator, field) is None
        assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.EVIDENCE_GAP
        return client

    monkeypatch.setattr(f"{M}.async_establish_ble_connection", connect)
    old_client.disconnect.side_effect = connect
    try:
        assert await coordinator._ensure_connected() is client
        client.start_notify.assert_awaited_once()
        client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, query, response=False)
        assert coordinator._identity_incomplete()
        assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.EVIDENCE_GAP
        for sibling, sibling_opcode in IDENTITY:
            if sibling != field:
                assert getattr(coordinator, sibling) == "legacy display"
                notify(coordinator, sibling_opcode, "99.99.99")
                assert (
                    video_control_states(coordinator.profile, coordinator)["white_balance"]
                    is CapabilityState.EVIDENCE_GAP
                )
        notify(coordinator, opcode, "9.08.06")
        assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.UNSUPPORTED
        assert not coordinator._identity_incomplete()
        client.write_gatt_char.reset_mock()
        await coordinator._send_identity_queries()
        client.write_gatt_char.assert_not_awaited()
    finally:
        await coordinator.disconnect()


async def test_malformed_notification_retries_until_valid(identity, monkeypatch):
    coordinator, field, opcode, query = identity
    notify(coordinator, opcode, "9.08.07")
    notify(coordinator, opcode, "malformed")
    assert getattr(coordinator, field) == "malformed"
    assert coordinator._identity_incomplete()
    assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.EVIDENCE_GAP
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client

    async def respond(_uuid, packet, **kwargs):
        assert packet == query
        notify(coordinator, opcode, "9.08.07")

    client.write_gatt_char.side_effect = respond
    ticks = 0

    async def state_queries(**kwargs):
        nonlocal ticks
        ticks += 1
        if ticks == 2:
            client.is_connected = False
        return True

    monkeypatch.setattr(coordinator, "_send_state_queries", state_queries)
    monkeypatch.setattr(f"{M}.asyncio.sleep", AsyncMock())
    await coordinator._keep_alive_loop()
    client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, query, response=False)
    assert coordinator._identity_retries == 1
    assert not coordinator._identity_incomplete()
    assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED


async def test_unconditioned_identity_remains_cached(hass, monkeypatch):
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6199", configuration_url="test")
    for field, _ in IDENTITY:
        setattr(coordinator, field, "legacy display")
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        await coordinator._ensure_connected()
        assert not coordinator._identity_incomplete()
        client.write_gatt_char.assert_not_awaited()
        assert all(getattr(coordinator, field) == "legacy display" for field, _ in IDENTITY)
    finally:
        await coordinator.disconnect()
