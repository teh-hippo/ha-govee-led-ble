"""Condition-bearing identity must come from the current connection, not cached display data."""

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import current_entry
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ha_govee_led_ble.const import DOMAIN, MODEL_PROFILES, ReadDomain, VideoFirmwareCondition
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.effect_contracts import CapabilityState
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_firmware_query,
    build_hardware_query,
    build_power,
    build_subordinate_query,
)
from custom_components.ha_govee_led_ble.govee_encryption import GoveeTransportError
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb
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
    previous_client = MagicMock(is_connected=True)
    coordinator._client = previous_client
    for name, _ in IDENTITY:
        setattr(coordinator, name, "legacy display")
    query = (
        build_firmware_query("H7000")
        if opcode == 0x06
        else build_hardware_query("H7000")
        if opcode == 0x07
        else build_subordinate_query(opcode, "H6199")
    )
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    return coordinator, field, opcode, query


def notify(coordinator, opcode, version):
    frame = bytearray(bytes((0xAA, opcode)) + (b"\x03" if opcode == 0x07 else b"") + version.encode("ascii"))
    frame.extend(bytes(19 - len(frame)))
    frame.append(xor_checksum(frame))
    coordinator._notify_callback(None, frame)


@pytest.mark.parametrize("stale_stream", [False, True])
async def test_reconnect_refreshes_only_condition_source(identity, monkeypatch, stale_stream, virtual_clock):
    coordinator, field, opcode, query = identity
    old_client = coordinator._client
    assert old_client is not None
    old_client.disconnect = AsyncMock()
    notify(coordinator, opcode, "9.08.07")
    old_client.is_connected = stale_stream
    assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED
    monkeypatch.setattr(coordinator, "_receive_is_stale", lambda: stale_stream)
    client = MagicMock(is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock())

    async def connect(*args, **kwargs):
        assert getattr(coordinator, field) == "9.08.07"
        assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED
        assert not coordinator.identity_fields_confirmed(frozenset({field}))
        return client

    monkeypatch.setattr(f"{M}.async_establish_ble_connection", connect)
    old_client.disconnect.side_effect = connect
    try:
        assert await coordinator._ensure_connected() is client
        client.start_notify.assert_awaited_once()
        client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, query, response=False)
        assert coordinator._identity_incomplete()
        assert getattr(coordinator, field) == "9.08.07"
        assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED
        assert not coordinator.identity_fields_confirmed(frozenset({field}))
        for sibling, sibling_opcode in IDENTITY:
            if sibling != field:
                assert getattr(coordinator, sibling) == "legacy display"
                notify(coordinator, sibling_opcode, "99.99.99")
                assert (
                    video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED
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
    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coordinator._client = client
    notify(coordinator, opcode, "9.08.07")
    notify(coordinator, opcode, "malformed")
    assert getattr(coordinator, field) == "9.08.07"
    assert coordinator._identity_incomplete()
    assert video_control_states(coordinator.profile, coordinator)["white_balance"] is CapabilityState.SUPPORTED

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
    coordinator.profile = replace(coordinator.profile, video_revision_policy=None, profile_identity_fields=frozenset())
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


@pytest.fixture
async def revision_control(hass, monkeypatch, request):
    model = getattr(request, "param", "H6181")
    firmware, hardware = ("1.03.00", "1.00.03") if model == "H6181" else ("1.08.06", "1.00.02")
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", model, configuration_url=None)
    if model == "H6117":
        coordinator.pact_type, coordinator.pact_code = 1, 1
        coordinator._resolve_device_profile()
    client = MagicMock(is_connected=True, services=[], start_notify=AsyncMock(), disconnect=AsyncMock())
    packets = []
    hardware_queries = 0
    replies = {
        build_firmware_query(model): b"\xaa\x06" + firmware.encode(),
        build_hardware_query(model): b"\xaa\x07\x03" + hardware.encode(),
    }

    async def write(_uuid, packet, **kwargs):
        nonlocal hardware_queries
        packets.append(packet)
        if packet == build_hardware_query(model):
            hardware_queries += 1
            if hardware_queries == 1:
                return
        if (reply := replies.get(packet)) is not None:
            body = reply.ljust(19, b"\x00")
            client.start_notify.call_args.args[1](None, body + bytes((xor_checksum(body),)))

    client.write_gatt_char = AsyncMock(side_effect=write)
    coordinator._reply_gate.timeout = 0
    monkeypatch.setattr(f"{M}.async_establish_ble_connection", AsyncMock(return_value=client))
    monkeypatch.setattr(f"{M}.bluetooth.async_last_service_info", lambda *args, **kwargs: None)
    monkeypatch.setattr(coordinator, "_start_keep_alive", MagicMock())
    try:
        yield coordinator, client, packets, replies
    finally:
        await coordinator.disconnect()


@pytest.mark.parametrize("fresh", [False, True])
@pytest.mark.parametrize("cached", [False, True])
async def test_foreground_recovers_missed_identity_before_selecting_colour_route(
    revision_control, fresh, cached, virtual_clock
):
    coordinator, _, packets, _ = revision_control
    if cached:
        coordinator._note_identity(fw_version="1.03.00", hw_version="1.00.03")
    if not fresh:
        await coordinator._ensure_connected()

    await coordinator.send_command(build_color_rgb(255, 0, 0, "H6181"))

    assert packets.count(build_hardware_query("H6181")) == 2
    assert [packet[:10] for packet in packets if packet[0] == 0x33] == [bytes.fromhex("330502ff000000000000")]
    assert coordinator.identity_fields_confirmed()
    assert coordinator._expected_state["rgb_color"][0] == (255, 0, 0)


@pytest.mark.parametrize("reply", [None, b"\xaa\x07\x03invalid"])
@pytest.mark.parametrize("attributes", [{"rgb_color": (255, 0, 0)}, {"effect": "off"}])
@pytest.mark.parametrize("cached_later", [False, True])
async def test_unresolved_colour_identity_does_not_partially_apply_light_request(
    revision_control, reply, attributes, cached_later, virtual_clock
):
    coordinator, _, packets, replies = revision_control
    if cached_later:
        coordinator.pact_type, coordinator.pact_code = 10, 1
        coordinator._note_identity(fw_version="1.03.00", hw_version="1.00.03")
    replies[build_hardware_query("H6181")] = reply
    light = GoveeBLELight(coordinator)
    light.hass = coordinator.hass
    light.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(**attributes, brightness=128)

    assert error.value.translation_key == "identity_not_ready"
    assert not any(packet[0] == 0x33 for packet in packets)
    assert coordinator.control_write_attempts == 0
    assert coordinator._expected_state == {}


@pytest.mark.parametrize("packet", [build_power(False, "H6181"), build_brightness(50, "H6181")])
async def test_identity_independent_controls_do_not_wait_for_optional_revision(revision_control, packet, virtual_clock):
    coordinator, _, packets, replies = revision_control
    await coordinator._ensure_connected()
    replies.clear()
    previous_queries = len(packets)

    await coordinator.send_command(packet)

    assert packets[previous_queries:] == [coordinator.profile.outbound_transform(packet)]
    assert not coordinator.identity_fields_confirmed()


@pytest.mark.parametrize("revision_control", ["H6117"], indirect=True)
@pytest.mark.parametrize("cached", [False, True])
async def test_shared_preparation_recovers_a_revision_gated_non_colour_command(revision_control, cached, virtual_clock):
    coordinator, _, packets, _ = revision_control
    if cached:
        coordinator._note_identity(fw_version="1.08.06", hw_version="1.00.02")
    await coordinator._ensure_connected()
    packet = build_brightness(50, "H6117")

    await coordinator.send_command(packet)

    assert packets.count(build_hardware_query("H6117")) == 2
    assert [packet for packet in packets if packet[0] == 0x33] == [coordinator.profile.outbound_transform(packet)]
    assert coordinator.identity_fields_confirmed()


@pytest.mark.parametrize("change", ["subscription", "client"])
async def test_identity_acquisition_cannot_authorise_a_replacement_session(revision_control, change, virtual_clock):
    coordinator, client, packets, _ = revision_control
    await coordinator._ensure_connected()
    original = client.write_gatt_char.side_effect

    async def write(*args, **kwargs):
        await original(*args, **kwargs)
        if change == "subscription":
            coordinator._notification_token = object()
        else:
            coordinator._client = MagicMock(is_connected=True)

    client.write_gatt_char.side_effect = write
    try:
        with pytest.raises(GoveeTransportError, match="identity_subscription_changed"):
            await coordinator.send_command(build_color_rgb(255, 0, 0, "H6181"))
        assert not any(packet[0] == 0x33 for packet in packets)
        assert coordinator.control_write_attempts == 0
    finally:
        coordinator._client = client


async def test_cancelled_identity_acquisition_never_attempts_the_control(revision_control, virtual_clock):
    coordinator, client, packets, _ = revision_control
    await coordinator._ensure_connected()
    waiting = asyncio.Event()
    blocked = asyncio.Event()

    async def write(*args, **kwargs):
        waiting.set()
        await blocked.wait()

    client.write_gatt_char.side_effect = write
    request = asyncio.create_task(coordinator.send_command(build_color_rgb(255, 0, 0, "H6181")))
    await waiting.wait()
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request
    assert not any(packet[0] == 0x33 for packet in packets)
    assert coordinator.control_write_attempts == 0
    assert not coordinator.identity_fields_confirmed()


@pytest.mark.parametrize("cached_later", [False, True])
async def test_static_recovery_qualifies_identity_before_its_first_control(
    revision_control, monkeypatch, cached_later, virtual_clock
):
    coordinator, _, packets, _ = revision_control
    if cached_later:
        coordinator.pact_type, coordinator.pact_code = 10, 1
        coordinator._note_identity(fw_version="1.03.00", hw_version="1.00.03")
    else:
        await coordinator._ensure_connected()
    state = replace(
        coordinator.capture_effect_control_state(),
        is_on=True,
        brightness_pct=50,
        rgb_color=(255, 0, 0),
        color_temp_kelvin=None,
    )
    monkeypatch.setattr(coordinator, "refresh_state", AsyncMock(return_value=True))

    assert await coordinator._restore_static_colour(state, True)

    assert packets.count(build_hardware_query("H6181")) == 2
    assert [packet[:10] for packet in packets if packet[0] == 0x33] == [
        bytes.fromhex("33010100000000000000"),
        bytes.fromhex("33048800000000000000"),
        bytes.fromhex("330502ff000000000000"),
    ]


@pytest.mark.parametrize("identity_available", [False, True])
async def test_injected_sequence_qualifies_identity_before_any_control(
    revision_control, identity_available, virtual_clock
):
    coordinator, client, packets, replies = revision_control
    await coordinator._ensure_connected()
    if not identity_available:
        replies.clear()

    async def writer(packet, **kwargs):
        async with coordinator._lock:
            await coordinator._async_write_packet(
                client, packet, arm_expected=True, before_write=kwargs.pop("write_guard", None), **kwargs
            )

    sequence = (build_power(True, "H6181"), build_color_rgb(255, 0, 0, "H6181"))
    if identity_available:
        await coordinator.async_write_effect_sequence(sequence, intent=ControlIntent.PREVIEW, writer=writer)
        assert [packet[:4] for packet in packets if packet[0] == 0x33] == [b"\x33\x01\x01\x00", b"\x33\x05\x02\xff"]
        assert coordinator.identity_fields_confirmed()
    else:
        with pytest.raises(HomeAssistantError) as error:
            await coordinator.async_write_effect_sequence(sequence, intent=ControlIntent.PREVIEW, writer=writer)
        assert error.value.translation_key == "identity_not_ready"
        assert not any(packet[0] == 0x33 for packet in packets)
        assert coordinator.control_write_attempts == 0


async def test_identity_change_during_reply_pacing_invalidates_prepared_control(
    revision_control, monkeypatch, virtual_clock
):
    coordinator, client, packets, _ = revision_control
    await coordinator._ensure_connected()
    await coordinator._async_require_identity(client, coordinator.profile.static_identity_fields)
    entered, release = asyncio.Event(), asyncio.Event()

    async def wait():
        entered.set()
        await release.wait()

    monkeypatch.setattr(coordinator._reply_gate, "wait", wait)
    request = asyncio.create_task(coordinator.send_command(build_color_rgb(255, 0, 0, "H6181")))
    await entered.wait()
    notify(coordinator, 0x06, "1.03.01")
    release.set()

    with pytest.raises(ValueError, match="context changed"):
        await request
    assert not any(packet[0] == 0x33 for packet in packets)
    assert coordinator.control_write_attempts == 0
    assert coordinator._expected_state == {}


@pytest.mark.parametrize("attributes", [{"effect": "off"}, {"rgb_color": (255, 0, 0)}])
async def test_complete_static_request_does_not_follow_a_readback_reconnect(
    revision_control, monkeypatch, attributes, virtual_clock
):
    coordinator, _, _, _ = revision_control
    await coordinator._ensure_connected()
    coordinator.is_on = True
    replacement = MagicMock(
        is_connected=True, start_notify=AsyncMock(), write_gatt_char=AsyncMock(), disconnect=AsyncMock()
    )
    light = GoveeBLELight(coordinator)
    light.hass = coordinator.hass
    light.async_write_ha_state = MagicMock()

    async def reconnect(**kwargs):
        await coordinator.disconnect()
        coordinator._client = replacement
        await coordinator._start_notify()
        notify(coordinator, 0x06, "1.03.00")
        notify(coordinator, 0x07, "1.00.03")

    monkeypatch.setattr(light, "_refresh_with_retry", reconnect)
    with pytest.raises(HomeAssistantError) as error:
        await light.async_turn_on(**attributes, brightness=128)
    assert error.value.translation_key == "partial_command"
    replacement.write_gatt_char.assert_not_awaited()
