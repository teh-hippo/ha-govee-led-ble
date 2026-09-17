"""Synthetic APK transport checks, not H6099 hardware qualification."""

import asyncio
import json
import os
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak import BleakError
from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dbus_fast.constants import MessageType
from habluetooth.wrappers import HaBleakClientWrapper

from custom_components.ha_govee_led_ble.advertisement import parse_govee_advertisement
from custom_components.ha_govee_led_ble.control_arbiter import ControlIntent
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_power, build_power_query
from custom_components.ha_govee_led_ble.govee_encryption import (
    KEY_COMMUNICATION,
    KEY_HANDSHAKE,
    GoveeCryptoError,
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
from custom_components.ha_govee_led_ble.transport import (
    ENCRYPTION_UUID,
    READ_UUID,
    WRITE_UUID,
    fragment_a3,
    xor_checksum,
)

KEY = bytes(range(16))
IV = bytes(range(8))
M = "custom_components.ha_govee_led_ble.coordinator"


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


@pytest.mark.parametrize("marker", [b"", b"\x01", b"\x02\x02", b"\x02\0", b"\x03\x01", b"\x01\x03"])
async def test_invalid_marker_never_becomes_plaintext(marker):
    session, device = GoveeEncryptionSession(), client(marker)
    with pytest.raises(GoveeCryptoError, match="selection_failed"):
        await session.async_select(device, advertised=False)
    device.services = []
    with pytest.raises(GoveeCryptoError):
        await session.async_select(device, advertised=False)
    with pytest.raises(GoveeCryptoError):
        session.encode(build_power(True))
    device.write_gatt_char.assert_not_awaited()


async def test_read_failure_has_no_raw_error_or_fallback():
    session, device = GoveeEncryptionSession(), client(b"\x01\x02")
    device.read_gatt_char.side_effect = RuntimeError("secret address/key payload")
    with pytest.raises(GoveeCryptoError) as err:
        await session.async_select(device, advertised=False)
    assert "secret" not in str(err.value)
    assert "secret" not in json.dumps(session.diagnostics())
    assert not session.ready


def test_advertisement_and_omissions(hass):
    positive = {0x8843: bytes.fromhex("ec010203")}
    assert parse_govee_advertisement(positive).supports_encryption
    assert parse_govee_advertisement({0x8843: b"\xec"}) is None
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H617A", configuration_url=None)
    for data in (positive, {}, {0x8803: bytes.fromhex("ec010203")}):
        coordinator._note_advertisement(SimpleNamespace(manufacturer_data=data))
        assert coordinator._advertised_encryption


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
    with pytest.raises(GoveeCryptoError):
        await session.async_negotiate(device)
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
    with pytest.raises(GoveeCryptoError):
        await session.async_negotiate(device)
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
    coordinator = GoveeBLECoordinator(hass, "11:22:33:44:55:66", "H6076", configuration_url=None)
    packet = build_power(True, "H6076")
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


@pytest.mark.parametrize("version", [1, 2])
async def test_disconnect_after_response_cannot_install_keys(version):
    session, device = GoveeEncryptionSession(), client(bytes((1, version)))
    await session.async_select(device, advertised=False)

    async def write(_uuid, frame, **_kwargs):
        session.decode(v1_reply(parse_v1_handshake(frame).opcode) if version == 1 else v2_reply())
        session.reset()  # A disconnect can land after the future resolves but before its waiter resumes.

    device.write_gatt_char.side_effect = write
    with pytest.raises(GoveeCryptoError):
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


@pytest.mark.parametrize("error, expected", [(RuntimeError, GoveeCryptoError), (BleakError, BleakError)])
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
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else GoveeCryptoError):
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
