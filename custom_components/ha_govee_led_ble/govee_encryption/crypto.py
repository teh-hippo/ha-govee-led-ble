"""AES-GCM primitives for the Govee "v3" (``0xE711``) BLE encryption scheme.

Pure functions -- no Bluetooth, no Home Assistant, no I/O -- so every claim here is
testable offline. :mod:`.session` holds the connection-scoped state.

Newer Govee devices wrap the classic 20-byte command frame in AES-128-GCM.
The protocol constants are shared across devices rather than secret or device-specific.
The per-device key is derived from the SKU and BLE MAC advertised by the device.
"""

from __future__ import annotations

import os
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Protocol-wide constants used by every device implementing this generation.
KEY_HANDSHAKE = bytes.fromhex("FC03783C7C42CB83E202A1643648AFF6")
KEY_DEVICE = bytes.fromhex("AE028B630BAE6ECC4BFF1B249E22F955")

MAGIC = 0xE7
CMD_SESSION = 0x11
TAG_LEN = 16
FRAME_LEN = 20

# EncryptionManagerV2.j() takes the single-frame path only when mtu > tagLen + 35. The
# fragmented fallback below that (0xE719/0xE71A) is documented in PROTOCOL.md section 7
# and deliberately not implemented: no device we can test negotiates an MTU that small.
MIN_MTU = TAG_LEN + 36

# On the wire the host counter starts at 2 and the device counter at 1. Confirmed against
# hardware; a frame that fails its tag check does not advance the device's replay state,
# so a failed handshake costs nothing and a retry starts from the same value.
HOST_COUNTER_START = 2

# Read-only marker characteristic carrying the encryption version. The write and notify
# UUIDs are the integration's existing WRITE_UUID/READ_UUID and are not repeated here.
UUID_ENC_VERSION = "00010203-0405-0607-0809-0a0b0c0d2b12"

# The only version this package implements. BgcInfoReader.g() also treats 1 as "encryption
# supported", but that is a different scheme and we have never seen a device report it.
ENCRYPTION_VERSION_AES_GCM = 2


class GoveeCryptoError(Exception):
    """Anything that goes wrong below. Callers fall back to plaintext."""


def parse_encryption_version(data: bytes | None) -> int:
    """Read the encryption version out of the ``2b12`` characteristic.

    Two observed formats exist::

        01 <version> ...
        02 <version> <flag> <pactType hi> <pactType lo> <pactCode> ...

    Returns 0 when the blob is absent, empty or in an unrecognised format -- that is the
    "not encrypted, use plaintext" answer.
    """
    if not data or len(data) < 2:
        return 0
    if data[0] in (1, 2):
        return data[1]
    return 0


def parse_bgc_info_v2(data: bytes) -> tuple[int, int] | None:
    """``(pactType, pactCode)`` from a format-2 ``2b12`` blob, else ``None``.

    The tested device returns the format-1 blob, which does not carry these keys.
    The same pair is also present in ``aa ef`` and BLE advertisement data.
    """
    if len(data) < 6 or data[0] != 2:
        return None
    return (data[3] << 8) | data[4], data[5]


def derive_device_key(sku: bytes, mac_wire_order: bytes) -> bytes:
    """``deviceKey = AES-ECB-Encrypt_KEY_DEVICE( (sku || mac) zero-padded to 16 )``.

    ``mac_wire_order`` must be handshake ``plaintext[13:19]`` exactly as received --
    little-endian relative to the usual display form. Reversing it into display order
    yields a plausible-looking key that fails every later tag check.
    """
    info = bytes(sku) + bytes(mac_wire_order)
    if len(info) > 16:
        raise GoveeCryptoError(f"device info too long: {len(info)}")
    block = bytearray(16)
    block[: len(info)] = info
    encryptor = Cipher(algorithms.AES(KEY_DEVICE), modes.ECB()).encryptor()  # noqa: S305
    return encryptor.update(bytes(block)) + encryptor.finalize()


def build_handshake(client_iv_key: bytes, iv: bytes | None = None, tag_len: int = TAG_LEN) -> bytes:
    """The ``0xE711`` request: ``[E7][11][01][iv 12][tagLen][gcm(ct||tag)]``.

    AAD is the frame's own first 16 bytes. ``iv`` is injectable for testing only;
    production callers leave it ``None`` so it comes from :func:`os.urandom`.
    """
    if len(client_iv_key) != 8:
        raise GoveeCryptoError("client ivKey must be 8 bytes")
    if iv is None:
        iv = os.urandom(12)
    header = bytes([MAGIC, CMD_SESSION, 0x01]) + bytes(iv) + bytes([tag_len])
    sealed = AESGCM(KEY_HANDSHAKE).encrypt(bytes(iv), bytes(client_iv_key), header)
    if tag_len != TAG_LEN:  # AESGCM always emits a 16-byte tag; truncate to the negotiated one
        sealed = sealed[: len(client_iv_key) + tag_len]
    return header + sealed


def is_handshake_response(frame: bytes) -> bool:
    """True for a ``0xE711`` reply, which must never reach the command decoder."""
    return len(frame) >= 2 and frame[0] == MAGIC and frame[1] == CMD_SESSION


def parse_handshake_response(frame: bytes) -> tuple[bytes, bytes, bytes]:
    """-> ``(device ivKey, sku, mac in wire order)``.

    The response carries no ``tagLen`` byte, so its AAD is 15 bytes rather than the
    request's 16 and its ciphertext starts one byte earlier.
    """
    frame = bytes(frame)
    if not is_handshake_response(frame) or len(frame) < 16:
        raise GoveeCryptoError(f"not a 0xE711 response: {frame[:4].hex()}")
    if frame[2] != 0x00:
        raise GoveeCryptoError(f"device refused key negotiation: status={frame[2]:#04x}")
    try:
        plain = AESGCM(KEY_HANDSHAKE).decrypt(frame[3:15], frame[15:], frame[:15])
    except Exception as err:  # InvalidTag and friends
        raise GoveeCryptoError(f"handshake response failed authentication: {err}") from err
    if len(plain) != 19:
        raise GoveeCryptoError(f"unexpected handshake plaintext length {len(plain)}")
    return plain[0:8], plain[8:13], plain[13:19]


def seal(plaintext: bytes, iv_key: bytes, device_key: bytes, counter: int) -> bytes:
    """``[counter 4 BE][gcm(ct||tag)]``, nonce = ``iv_key || counter``, AAD = counter."""
    ctr = struct.pack(">I", counter)
    return ctr + AESGCM(device_key).encrypt(iv_key + ctr, bytes(plaintext), ctr)


def unseal(frame: bytes, iv_key: bytes, device_key: bytes) -> tuple[int, bytes]:
    """Inverse of :func:`seal`. Raises :class:`GoveeCryptoError` on a bad tag."""
    frame = bytes(frame)
    if len(frame) < 5:
        raise GoveeCryptoError("frame too short")
    ctr = frame[:4]
    try:
        plain = AESGCM(device_key).decrypt(iv_key + ctr, frame[4:], ctr)
    except Exception as err:
        raise GoveeCryptoError(f"frame failed authentication: {err}") from err
    return struct.unpack(">I", ctr)[0], plain
