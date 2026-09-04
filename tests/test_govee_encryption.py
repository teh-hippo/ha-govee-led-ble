"""Offline tests for the Govee ``0xE711`` AES-GCM and ``0xE7 01`` encryption packages.

Device identity here is invented. The one real device this scheme has been driven against
contributes captured *frames* -- a handshake request, which carries only a random IV and an
encrypted session nonce, and the ``2b12`` marker, which is a version byte and padding.
Neither carries a MAC, and the derived key of the real device appears nowhere.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakClient
from bleak.backends.device import BLEDevice
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from custom_components.ha_govee_led_ble.ble_device_resolver import BLEDeviceResolution, BLEDeviceResolver
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_power,
    build_power_query,
)
from custom_components.ha_govee_led_ble.govee_encryption import crypto, crypto_v1
from custom_components.ha_govee_led_ble.govee_encryption import session as session_module
from custom_components.ha_govee_led_ble.govee_encryption.session import (
    BLE_DEFAULT_MTU,
    HANDSHAKE_TIMEOUT,
    GoveeEncryptionSession,
)
from custom_components.ha_govee_led_ble.transport import READ_UUID, WRITE_UUID
from tests.govee_device_double import GoveeDeviceDouble, NotifyCallback

_COORDINATOR = "custom_components.ha_govee_led_ble.coordinator"
TEST_ADDRESS = "AA:BB:CC:DD:EE:FF"
TEST_CONFIGURATION_URL = "homeassistant://ha-govee-led-ble/editor/test-entry"

# Any well-formed 20-byte frame will do for the "does a sealed round trip preserve bytes"
# assertions. A power query is used because it is the frame the keep-alive really sends.
KEEP_ALIVE = build_power_query()


def make_ble_device(address: str = TEST_ADDRESS) -> BLEDevice:
    return BLEDevice(address, f"Govee_mock_{address}", {})


def make_resolver(address: str = TEST_ADDRESS) -> MagicMock:
    """A device resolver that always resolves, without touching the bluetooth manager."""
    resolver = MagicMock(spec=BLEDeviceResolver)
    resolver.async_resolve = AsyncMock(return_value=BLEDeviceResolution(make_ble_device(address), BleakClient))
    return resolver


def patch_connection(client: object):
    """Patch the coordinator's connect step to hand back ``client``.

    Pair it with ``device_resolver=make_resolver()`` on the coordinator: the resolver is
    constructed in ``__init__``, so patching the class afterwards is too late.
    """
    return patch(f"{_COORDINATOR}.establish_connection", return_value=client)


# --- invented device identity ------------------------------------------------------------
SKU = b"H66A0"
MAC = bytes.fromhex("112233445566")
DEVICE_KEY = bytes.fromhex("5b4fe29c474a45bae18a4c09c1c969d6")
IV_KEY = bytes.fromhex("0001020304050607")

# --- captured, and free of device identity -------------------------------------------------
# One 0xE711 request as the iOS app sent it. Its only variable content is the 12-byte IV and
# the AES-GCM-sealed 8-byte client nonce, both freshly random per session.
HANDSHAKE_REQUEST = bytes.fromhex("e7110138fab547fcce6a692dd093c710712d825424fe256368b02083d7b367f36b8595c12c60cd92")
HANDSHAKE_REQUEST_IV = HANDSHAKE_REQUEST[3:15]
HANDSHAKE_CLIENT_IV_KEY = bytes.fromhex("fe332c0eca3eb701")
# The marker exactly as an H66A0 returns it: format 1, version 2, zero-padded to 20 bytes.
MARKER_BLOB = bytes.fromhex("0102000000000000000000000000000000000000")


def make_handshake_response(device_iv_key: bytes, *, sku: bytes = SKU, mac: bytes = MAC, status: int = 0) -> bytes:
    """Build the reply the device sends. AAD is 15 bytes: there is no tagLen field."""
    iv = bytes(range(12))
    header = bytes([crypto.MAGIC, crypto.CMD_SESSION, status]) + iv
    return header + AESGCM(crypto.KEY_HANDSHAKE).encrypt(iv, device_iv_key + sku + mac, header)


# ============================================================== crypto: key derivation


def test_key_derivation_known_vector():
    assert crypto.derive_device_key(SKU, MAC) == DEVICE_KEY


def test_key_derivation_mac_byte_order_matters():
    """The classic trap: the MAC is consumed in wire order, not display order."""
    assert crypto.derive_device_key(SKU, MAC[::-1]) != DEVICE_KEY


def test_key_derivation_rejects_oversized_device_info():
    with pytest.raises(crypto.GoveeCryptoError):
        crypto.derive_device_key(b"SKUTHATISFARTOOLONG", MAC)


# ============================================================== crypto: handshake


def test_handshake_build_reproduces_the_captured_request():
    assert crypto.build_handshake(HANDSHAKE_CLIENT_IV_KEY, HANDSHAKE_REQUEST_IV) == HANDSHAKE_REQUEST


def test_handshake_request_is_forty_bytes_with_a_sixteen_byte_tag():
    assert len(crypto.build_handshake(HANDSHAKE_CLIENT_IV_KEY)) == 40


def test_handshake_request_honours_a_twelve_byte_tag():
    """Android negotiates a 96-bit tag, which shortens the request to 36 bytes."""
    assert len(crypto.build_handshake(HANDSHAKE_CLIENT_IV_KEY, tag_len=12)) == 36


def test_handshake_request_rejects_a_wrong_length_nonce():
    with pytest.raises(crypto.GoveeCryptoError):
        crypto.build_handshake(b"\x00" * 7)


def test_handshake_response_round_trip():
    device_iv_key = bytes.fromhex("a0a1a2a3a4a5a6a7")
    frame = make_handshake_response(device_iv_key)
    assert len(frame) == 50
    assert crypto.parse_handshake_response(frame) == (device_iv_key, SKU, MAC)


def test_handshake_response_rejects_a_refusal():
    with pytest.raises(crypto.GoveeCryptoError, match="refused"):
        crypto.parse_handshake_response(make_handshake_response(IV_KEY, status=2))


def test_handshake_response_rejects_bad_magic():
    with pytest.raises(crypto.GoveeCryptoError, match="not a 0xE711"):
        crypto.parse_handshake_response(b"\x00" * 50)


def test_handshake_response_rejects_tampered_ciphertext():
    frame = bytearray(make_handshake_response(IV_KEY))
    frame[20] ^= 0x01
    with pytest.raises(crypto.GoveeCryptoError, match="authentication"):
        crypto.parse_handshake_response(bytes(frame))


def test_handshake_response_rejects_a_wrong_plaintext_length():
    iv = bytes(range(12))
    header = bytes([crypto.MAGIC, crypto.CMD_SESSION, 0]) + iv
    frame = header + AESGCM(crypto.KEY_HANDSHAKE).encrypt(iv, b"short", header)
    with pytest.raises(crypto.GoveeCryptoError, match="plaintext length"):
        crypto.parse_handshake_response(frame)


# ============================================================== crypto: data frames


def test_seal_unseal_round_trip():
    packet = build_power(True)
    sealed = crypto.seal(packet, IV_KEY, DEVICE_KEY, 7)
    assert crypto.unseal(sealed, IV_KEY, DEVICE_KEY) == (7, packet)


def test_sealed_frame_is_the_captured_shape():
    """4 counter bytes + 20 plaintext + 16 tag, which is what the capture shows."""
    assert len(crypto.seal(build_power(True), IV_KEY, DEVICE_KEY, 2)) == 40


def test_the_counter_is_authenticated_not_merely_prefixed():
    sealed = bytearray(crypto.seal(build_power(True), IV_KEY, DEVICE_KEY, 2))
    sealed[3] ^= 0x01
    with pytest.raises(crypto.GoveeCryptoError):
        crypto.unseal(bytes(sealed), IV_KEY, DEVICE_KEY)


def test_unseal_rejects_the_wrong_direction_nonce():
    """Each direction has its own ivKey; swapping them fails every frame."""
    sealed = crypto.seal(build_power(True), IV_KEY, DEVICE_KEY, 2)
    with pytest.raises(crypto.GoveeCryptoError):
        crypto.unseal(sealed, bytes(8), DEVICE_KEY)


def test_unseal_rejects_a_truncated_frame():
    with pytest.raises(crypto.GoveeCryptoError, match="too short"):
        crypto.unseal(b"\x00\x00\x00\x02", IV_KEY, DEVICE_KEY)


# ============================================================== crypto: the 2b12 marker


@pytest.mark.parametrize(
    ("blob", "expected"),
    [
        (MARKER_BLOB, 2),  # format 1, as the H66A0 really answers
        (bytes.fromhex("0102"), 2),
        (bytes.fromhex("020201000a03"), 2),  # observed format 2
        (bytes.fromhex("0101"), 1),  # a different scheme, not this one
        (bytes.fromhex("0100"), 0),
        (bytes.fromhex("ff02"), 0),  # unknown format tag
        (b"\x01", 0),
        (b"", 0),
        (None, 0),
    ],
)
def test_parse_encryption_version(blob, expected):
    assert crypto.parse_encryption_version(blob) == expected


def test_bgc_info_v2_carries_pact_type_and_code():
    assert crypto.parse_bgc_info_v2(bytes.fromhex("020201000a03")) == (10, 3)


def test_bgc_info_v2_absent_from_the_format_one_blob():
    assert crypto.parse_bgc_info_v2(MARKER_BLOB) is None
    assert crypto.parse_bgc_info_v2(bytes.fromhex("0202")) is None


# ============================================================== a synthetic encrypted device


class FakeCharacteristic:
    """Stands in for the one entry of the service table the session looks up."""


class FakeServices:
    def __init__(self, *, has_marker: bool) -> None:
        self._has_marker = has_marker

    def get_characteristic(self, uuid: str) -> FakeCharacteristic | None:
        if uuid == crypto.UUID_ENC_VERSION and self._has_marker:
            return FakeCharacteristic()
        return None


class EncryptedDevice:
    """A bleak-shaped client wrapping :class:`GoveeDeviceSim` in the 0xE711 scheme.

    The device half of the protocol, so the tests exercise the real thing rather than a
    mirror of the implementation: it derives the key from its own SKU and MAC, answers the
    handshake with its own nonce, and runs its own counter from 1.
    """

    def __init__(
        self,
        strip: GoveeDeviceDouble | None = None,
        *,
        marker: bytes | None = MARKER_BLOB,
        answer_handshake: bool = True,
        status: int = 0,
        mtu_size: int = 512,
        read_error: Exception | None = None,
    ) -> None:
        self.strip = strip if strip is not None else GoveeDeviceDouble("H617A")
        self.marker, self.answer_handshake, self.status = marker, answer_handshake, status
        self.mtu_size, self.read_error = mtu_size, read_error
        self.is_connected = True
        self.device_iv_key = bytes.fromhex("a0a1a2a3a4a5a6a7")
        self.plaintext_writes: list[bytes] = []
        self.raw_writes: list[bytes] = []
        self._notify: NotifyCallback | None = None
        self._client_iv_key: bytes | None = None
        self._device_key: bytes | None = None
        self._counter = 1

    @property
    def services(self) -> FakeServices:
        return FakeServices(has_marker=self.marker is not None)

    async def read_gatt_char(self, uuid: str) -> bytearray:
        if self.read_error is not None:
            raise self.read_error
        assert uuid == crypto.UUID_ENC_VERSION
        assert self.marker is not None
        return bytearray(self.marker)

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        assert uuid == READ_UUID
        self._notify = callback

    async def disconnect(self) -> None:
        self.is_connected = False

    def _emit(self, frame: bytes) -> None:
        if self._notify is not None:
            self._notify(None, bytearray(frame))

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        assert uuid == WRITE_UUID
        data = bytes(data)
        self.raw_writes.append(data)
        if crypto.is_handshake_response(data):
            plain = AESGCM(crypto.KEY_HANDSHAKE).decrypt(data[3:15], data[16:], data[:16])
            self._client_iv_key = plain
            self._device_key = crypto.derive_device_key(SKU, MAC)
            if self.answer_handshake:
                self._emit(make_handshake_response(self.device_iv_key, status=self.status))
            return
        if self.marker is None:
            # A device that never offered encryption: it reads the frame as it arrives.
            self.plaintext_writes.append(data)
            for reply in self.strip.handle_write(data):
                self._emit(reply)
            return
        if self._device_key is None or self._client_iv_key is None:
            # Plaintext arriving at a device that wanted a key: real hardware ignores it.
            self.plaintext_writes.append(data)
            return
        _counter, packet = crypto.unseal(data, self._client_iv_key, self._device_key)
        self.plaintext_writes.append(packet)
        for reply in self.strip.handle_write(packet):
            self._emit(crypto.seal(reply, self.device_iv_key, self._device_key, self._counter))
            self._counter += 1


# ============================================================== session negotiation


async def test_negotiation_end_to_end_against_a_synthetic_device():
    device = EncryptedDevice()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert session.active
    assert session.sku == "H66A0"
    assert session.encryption_version == 2


async def test_a_negotiated_session_encrypts_writes_and_decrypts_notifications():
    device = EncryptedDevice()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    received: list[bytes] = []

    def on_notify(_sender, data):
        if (frame := session.decode(bytes(data))) is not None:
            received.append(frame)

    await device.start_notify(READ_UUID, on_notify)
    await session.async_negotiate(device)

    packet = build_power(True)
    await device.write_gatt_char(WRITE_UUID, session.encode(packet))
    assert device.raw_writes[-1] != packet, "the frame reached the wire in the clear"
    assert device.plaintext_writes[-1] == packet, "the device could not read the frame"

    await device.write_gatt_char(WRITE_UUID, session.encode(KEEP_ALIVE))
    assert received, "no status reply survived decryption"
    assert received[-1][0] == 0xAA


async def test_the_host_counter_starts_at_two_and_advances_per_frame():
    device = EncryptedDevice()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    counters = [int.from_bytes(session.encode(build_power(True))[:4], "big") for _ in range(3)]
    assert counters == [crypto.HOST_COUNTER_START, crypto.HOST_COUNTER_START + 1, crypto.HOST_COUNTER_START + 2]


async def test_a_device_without_the_marker_stays_on_the_plaintext_path():
    """The H617A and H6199 case: no 2b12 characteristic, so nothing is even read."""
    device = EncryptedDevice(marker=None)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await session.async_negotiate(device)

    assert not session.active
    # One frame, and exactly one: the v1 probe. Negotiation used to put NOTHING on the wire
    # for a device without a v2 marker, and that invariant is deliberately given up here --
    # a v1 device is indistinguishable from a plaintext one until it is asked, and sending it
    # plaintext instead means a light that connects and silently does nothing.
    assert len(device.raw_writes) == 1
    assert crypto_v1.parse_negotiation_frame(device.raw_writes[0])[0] == crypto_v1.CMD_SESSION_KEY
    packet = build_brightness(40)
    assert session.encode(packet) == packet
    assert session.decode(packet) == packet


@pytest.mark.parametrize("marker", [bytes.fromhex("0101"), bytes.fromhex("0100"), b"", bytes.fromhex("ff02")])
async def test_any_marker_other_than_version_two_falls_back_to_plaintext(marker):
    device = EncryptedDevice(marker=marker)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await session.async_negotiate(device)

    assert not session.active
    assert len(device.raw_writes) == 1, "the v1 probe is the only frame negotiation may send"


async def test_a_failing_marker_read_falls_back_to_plaintext():
    device = EncryptedDevice(read_error=RuntimeError("characteristic read failed"))
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await session.async_negotiate(device)

    assert not session.active


async def test_a_refused_handshake_falls_back_to_plaintext():
    device = EncryptedDevice(status=2)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert not session.active
    packet = build_power(True)
    assert session.encode(packet) == packet


async def test_a_silent_device_times_out_and_falls_back_to_plaintext():
    device = EncryptedDevice(answer_handshake=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    with patch(
        "custom_components.ha_govee_led_ble.govee_encryption.session.HANDSHAKE_TIMEOUT",
        0.01,
    ):
        await session.async_negotiate(device)

    assert not session.active
    assert HANDSHAKE_TIMEOUT == 6.0, "the app's own 6000 ms budget"


async def test_a_genuinely_small_mtu_refuses_before_writing_anything():
    device = EncryptedDevice(mtu_size=crypto.MIN_MTU - 1)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await session.async_negotiate(device)

    assert not session.active
    assert device.raw_writes == []


async def test_the_unacquired_bluez_default_mtu_is_read_as_unknown_not_as_too_small():
    """The regression that would silently disable encryption on every Home Assistant OS box.

    bleak's BlueZ backend reports 23 until its private _acquire_mtu() runs, and nothing in
    Home Assistant calls it. The real MTU on the hardware this was developed against is 512.
    """
    assert BLE_DEFAULT_MTU < crypto.MIN_MTU
    device = EncryptedDevice(mtu_size=BLE_DEFAULT_MTU)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert session.active


async def test_an_unknown_mtu_is_also_read_as_unknown():
    device = EncryptedDevice(mtu_size=0)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert session.active


async def test_a_tampered_notification_is_dropped_rather_than_parsed():
    device = EncryptedDevice()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    good = crypto.seal(KEEP_ALIVE, device.device_iv_key, crypto.derive_device_key(SKU, MAC), 1)
    tampered = bytearray(good)
    tampered[-1] ^= 0x01
    assert session.decode(bytes(tampered)) is None
    assert session.decode(good) == KEEP_ALIVE


async def test_an_unexpected_handshake_frame_is_swallowed_not_parsed_as_a_command():
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    assert session.decode(make_handshake_response(IV_KEY)) is None


async def test_reset_forgets_the_session_so_a_reconnect_renegotiates():
    device = EncryptedDevice()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)
    assert session.active

    session.reset()
    assert not session.active
    assert session.sku is None
    packet = build_power(True)
    assert session.encode(packet) == packet

    await session.async_negotiate(device)
    assert session.active
    assert int.from_bytes(session.encode(packet)[:4], "big") == crypto.HOST_COUNTER_START


async def test_reset_cancels_a_handshake_still_in_flight():
    device = EncryptedDevice(answer_handshake=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    task = asyncio.create_task(session.async_negotiate(device))
    await asyncio.sleep(0)
    session.reset()
    await task
    assert not session.active


# ============================================================== the real coordinator


@pytest.fixture
def encrypted_coordinator(hass):
    return GoveeBLECoordinator(
        hass,
        "AA:BB:CC:DD:EE:FF",
        "H66A0",
        configuration_url=TEST_CONFIGURATION_URL,
        device_resolver=make_resolver(),
    )


# ============================================================== log diagnosability


async def test_a_timeout_says_what_timed_out_and_what_was_heard(caplog):
    """A user reporting this has the log and nothing else, so the log has to be enough.

    asyncio's TimeoutError stringifies to the empty string, so the naive
    "negotiation failed (%s)" renders as "negotiation failed ()" -- true, and useless. The
    notification count is what separates "the device never answered" from "notifications
    are not reaching us", which are different faults with identical symptoms.
    """
    device = EncryptedDevice(answer_handshake=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    with (
        caplog.at_level(logging.WARNING),
        patch("custom_components.ha_govee_led_ble.govee_encryption.session.HANDSHAKE_TIMEOUT", 0.01),
    ):
        await session.async_negotiate(device)

    assert not session.active
    message = caplog.text
    assert "no handshake response within" in message
    assert "0 notification(s)" in message
    assert "MTU reported as 512" in message
    assert "()" not in message, "an empty reason leaked into the log"


async def test_a_refusal_names_the_status_byte(caplog):
    device = EncryptedDevice(status=2)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    with caplog.at_level(logging.WARNING):
        await session.async_negotiate(device)

    assert "refused key negotiation" in caplog.text
    # The frame reached us, which is the fact that rules out a dead notify path.
    assert "1 notification(s)" in caplog.text


# --- encryption v1 -----------------------------------------------------------------
#
# The scheme an H61F5 forced into view: no 2b12 characteristic at all, so the marker reads
# as 0 and looks exactly like the plaintext models, while every plaintext frame sent to it is
# accepted at ATT and silently ignored. These pin the third branch of the cascade.

# Invented, not captured. A v1 session key is negotiated per connection and expires with it,
# but it is still key material recovered from one person's device, and the first draft of this
# file used the real one -- which would have published it. Sixteen bytes chosen to be obviously
# synthetic; nothing here depends on the value.
V1_SESSION_KEY = bytes.fromhex("00112233445566778899aabbccddeeff")


class V1Device:
    """A device that speaks the 0xE7 01 / 0xE7 02 scheme and has no 2b12 characteristic."""

    def __init__(self, *, answer: bool = True, confirm: bool = True) -> None:
        self.answer, self.confirm = answer, confirm
        self.is_connected = True
        self.mtu_size = 512
        self.raw_writes: list[bytes] = []
        self.plaintext_writes: list[bytes] = []
        self._notify: NotifyCallback | None = None
        self._key: bytes | None = None

    @property
    def services(self) -> FakeServices:
        return FakeServices(has_marker=False)

    async def read_gatt_char(self, uuid: str) -> bytearray:  # pragma: no cover - never reached
        raise AssertionError("a device with no marker must not be read")

    async def start_notify(self, uuid: str, callback: NotifyCallback) -> None:
        self._notify = callback

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        self.raw_writes.append(bytes(data))
        if self._notify is None:
            raise AssertionError("start_notify must be wired before negotiating")
        parsed = crypto_v1.parse_negotiation_frame(bytes(data))
        if parsed is not None and self._key is None:
            command, _plain = parsed
            if command == crypto_v1.CMD_SESSION_KEY and self.answer:
                reply = bytearray(20)
                reply[0], reply[1] = crypto_v1.MAGIC, crypto_v1.CMD_SESSION_KEY
                reply[2:18] = V1_SESSION_KEY
                reply[19] = crypto_v1.xor_checksum(bytes(reply))
                self._notify(None, bytearray(crypto_v1.encrypt(bytes(reply), crypto_v1.KEY_COMMUNICATION)))
            elif command == crypto_v1.CMD_CONFIRM:
                self._key = V1_SESSION_KEY
                if self.confirm:
                    ack = bytearray(20)
                    ack[0], ack[1] = crypto_v1.MAGIC, crypto_v1.CMD_CONFIRM
                    ack[19] = crypto_v1.xor_checksum(bytes(ack))
                    self._notify(None, bytearray(crypto_v1.encrypt(bytes(ack), crypto_v1.KEY_COMMUNICATION)))
            return
        self.plaintext_writes.append(crypto_v1.decrypt(bytes(data), V1_SESSION_KEY))

    def push(self, plaintext: bytes) -> None:
        # Narrowed rather than ignored: write_gatt_char above already refuses to run before
        # start_notify has wired the callback, so an unwired push is a test-setup bug and should
        # say so, not fail later inside a None call.
        assert self._notify is not None, "start_notify must be wired before pushing"
        self._notify(None, bytearray(crypto_v1.encrypt(plaintext, V1_SESSION_KEY)))


def test_the_v1_transform_is_a_round_trip_and_preserves_length():
    """Length preservation is the property that tells v1 from v2 on the wire.

    v2 seals a 20-byte command into 40; v1 leaves it at 20, because whole blocks go through
    AES-ECB and only the 4-byte remainder is XORed with RC4.
    """
    packet = build_brightness(40)
    sealed = crypto_v1.encrypt(packet, V1_SESSION_KEY)
    assert len(sealed) == len(packet) == 20
    assert sealed != packet
    assert crypto_v1.decrypt(sealed, V1_SESSION_KEY) == packet


def test_the_rc4_tail_is_constant_across_frames():
    """Pins the weakness that identified the scheme before its key was known.

    RC4 is re-keyed for every frame, so the keystream over bytes 16..19 never advances. Two
    zero-padded frames therefore agree on bytes 16..18, which is what showed up in the
    capture as a repeating `9a 89 76` tail.
    """
    one = crypto_v1.encrypt(build_brightness(10), V1_SESSION_KEY)
    two = crypto_v1.encrypt(build_brightness(90), V1_SESSION_KEY)
    # The PROPERTY is asserted, not a literal keystream. The expected tail is a function of the
    # key, so hardcoding one would either pin an invented value that proves nothing or -- as an
    # earlier draft of this file did -- publish the keystream of a real device's session.
    assert one[16:19] == two[16:19]
    assert one[16:19] == crypto_v1._rc4(b"\x00" * 4, V1_SESSION_KEY)[:3]


async def test_a_v1_device_negotiates_and_round_trips(monkeypatch):
    device = V1Device()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert session.active
    assert session.encryption_version == crypto_v1.ENCRYPTION_VERSION_V1
    packet = build_brightness(40)
    await device.write_gatt_char(WRITE_UUID, session.encode(packet))
    assert device.plaintext_writes[-1] == packet, "the device could not read what we sent it"
    device.push(packet)


async def test_a_v1_device_that_never_answers_falls_back_to_plaintext(monkeypatch):
    monkeypatch.setattr(session_module, "V1_HANDSHAKE_TIMEOUT", 0.05)
    device = V1Device(answer=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert not session.active
    packet = build_brightness(40)
    assert session.encode(packet) == packet
    assert session.decode(packet) == packet


async def test_a_v1_device_that_skips_the_confirm_ack_still_encrypts(monkeypatch):
    """The ack is courtesy, not consent: the session key arrived in the previous frame."""
    monkeypatch.setattr(session_module, "V1_CONFIRM_TIMEOUT", 0.05)
    device = V1Device(confirm=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    assert session.active


async def test_a_v1_frame_failing_its_checksum_is_dropped():
    """v1 has no authentication tag, so the XOR checksum is the only integrity signal."""
    device = V1Device()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))
    await session.async_negotiate(device)

    corrupt = bytearray(build_brightness(40))
    corrupt[19] ^= 0xFF
    assert session.decode(crypto_v1.encrypt(bytes(corrupt), V1_SESSION_KEY)) is None


def test_the_v1_probe_timeout_stays_small():
    """Every plaintext device pays this on every connection, so it is a user-facing number."""
    assert session_module.V1_HANDSHAKE_TIMEOUT <= 2.0


async def test_the_v1_probe_is_not_repeated_once_a_device_has_declined(monkeypatch):
    """A device's encryption generation does not change between reconnects.

    Reconnects are frequent, so probing on every one would make the cost permanent for every
    plaintext device. Probing once per coordinator makes it a rounding error.
    """
    monkeypatch.setattr(session_module, "V1_HANDSHAKE_TIMEOUT", 0.05)
    device = V1Device(answer=False)
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))

    await session.async_negotiate(device)
    assert len(device.raw_writes) == 1
    session.reset()  # what a disconnect does
    await session.async_negotiate(device)
    assert len(device.raw_writes) == 1, "the v1 probe was repeated after a reconnect"
    assert not session.active


async def test_a_probe_that_errored_is_not_cached_as_a_refusal(monkeypatch):
    """Only the device saying nothing is evidence about the device.

    A write that raised says something about the link, so caching it would let one transient
    failure switch encryption off for the rest of the session.
    """
    monkeypatch.setattr(session_module, "V1_HANDSHAKE_TIMEOUT", 0.05)
    device = V1Device()
    session = GoveeEncryptionSession("AA:BB:CC:DD:EE:FF")
    await device.start_notify(READ_UUID, lambda _s, data: session.decode(bytes(data)))

    async def boom(*_args, **_kwargs):
        raise RuntimeError("link dropped")

    monkeypatch.setattr(device, "write_gatt_char", boom)
    await session.async_negotiate(device)
    assert not session.active
    assert not session._v1_ruled_out, "a link error must not be remembered as 'not a v1 device'"

    monkeypatch.undo()
    await session.async_negotiate(device)
    assert session.active, "the device must still be reachable as v1 after a transient failure"
