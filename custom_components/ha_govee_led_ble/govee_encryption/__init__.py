"""Govee APK crypto primitives; wire layouts belong to speculative Kaitai.

V1 is the vendor's unauthenticated AES-ECB/RC4 scheme, not modern secure
messaging. The app-global constants are not per-device secrets.
"""

import io
import os
from importlib import import_module
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from kaitaistruct import KaitaiStream

from ..transport import xor_checksum

GoveeEncryption = import_module(
    "custom_components.ha_govee_led_ble.generated_protocol.govee_encryption"
).GoveeEncryption

KEY_COMMUNICATION = bytes.fromhex("4d616b696e674c696665536d61727465")
KEY_HANDSHAKE = bytes.fromhex("fc03783c7c42cb83e202a1643648aff6")
KEY_DEVICE = bytes.fromhex("ae028b630bae6ecc4bff1b249e22f955")
TAG_LEN = 16
MIN_MTU = 53  # The 50-byte handshake reply must fit ATT's MTU minus 3.


class GoveeCryptoError(ValueError):
    """A fixed, non-secret transport rejection. Never authorize fallback."""


def parse_wire(kind: str, data: bytes) -> Any:
    """Read a schema-owned structure without exposing parser exception payloads."""
    try:
        stream = KaitaiStream(io.BytesIO(data))
        parsed = getattr(GoveeEncryption, kind)(stream)
        parsed._read()
        if not stream.is_eof():
            raise GoveeCryptoError("invalid_frame_length")
        return parsed
    except Exception:
        raise GoveeCryptoError("invalid_frame") from None


def v1_transform(data: bytes, key: bytes, *, encrypt: bool) -> bytes:
    if len(key) != 16:
        raise GoveeCryptoError("invalid_key_length")
    boundary = len(data) // 16 * 16
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    result = ctx.update(data[:boundary]) + ctx.finalize()
    if boundary < len(data):
        tail = Cipher(ARC4(key), mode=None).encryptor()
        result += tail.update(data[boundary:]) + tail.finalize()
    return result


def build_v1_handshake(opcode: int) -> bytes:
    # Crypto framing, matching Controller4Aes.a/e/f. Both phases use the app key.
    if opcode not in (1, 2):
        raise GoveeCryptoError("invalid_handshake_opcode")
    body = bytes((0xE7, opcode)) + os.urandom(17)
    return v1_transform(body + bytes((xor_checksum(body),)), KEY_COMMUNICATION, encrypt=True)


def parse_v1_handshake(frame: bytes) -> Any:
    if len(frame) != 20:
        raise GoveeCryptoError("invalid_handshake_length")
    plain = v1_transform(frame, KEY_COMMUNICATION, encrypt=False)
    parsed = parse_wire("V1Handshake", plain)
    if parsed.magic != 0xE7 or parsed.opcode not in (1, 2) or xor_checksum(plain):
        raise GoveeCryptoError("invalid_handshake")
    return parsed


def build_v2_handshake(iv_key: bytes, *, nonce: bytes | None = None, tag_len: int = TAG_LEN) -> bytes:
    if len(iv_key) != 8 or tag_len != TAG_LEN:
        raise GoveeCryptoError("unsupported_handshake_parameters")
    nonce = os.urandom(12) if nonce is None else nonce
    if len(nonce) != 12:
        raise GoveeCryptoError("invalid_nonce_length")
    header = b"\xe7\x11\x01" + nonce + bytes((TAG_LEN,))
    return header + AESGCM(KEY_HANDSHAKE).encrypt(nonce, iv_key, header)


def parse_v2_handshake(frame: bytes) -> tuple[bytes, bytes]:
    parsed = parse_wire("V2Response", frame)
    if parsed.magic != 0xE7 or parsed.opcode != 0x11 or parsed.status != 0:
        raise GoveeCryptoError("invalid_handshake")
    header = bytes((parsed.magic, parsed.opcode, parsed.status)) + parsed.nonce
    try:
        plain = AESGCM(KEY_HANDSHAKE).decrypt(parsed.nonce, parsed.sealed, header)
    except InvalidTag, ValueError:
        raise GoveeCryptoError("handshake_authentication_failed") from None
    identity = parse_wire("V2Identity", plain)
    info = identity.sku + identity.mac_wire_order
    ctx = Cipher(algorithms.AES(KEY_DEVICE), modes.ECB()).encryptor()  # noqa: S305
    key = ctx.update(info.ljust(16, b"\0")) + ctx.finalize()
    return identity.iv_key, key


def seal(plain: bytes, iv_key: bytes, key: bytes, counter: int) -> bytes:
    if not 1 <= counter <= 0xFFFFFFFF:
        raise GoveeCryptoError("counter_exhausted")
    if len(iv_key) != 8 or len(key) != 16:
        raise GoveeCryptoError("invalid_key_length")
    ctr = counter.to_bytes(4, "big")
    return ctr + AESGCM(key).encrypt(iv_key + ctr, plain, ctr)


def unseal(frame: bytes, iv_key: bytes, key: bytes) -> tuple[int, bytes]:
    parsed = parse_wire("V2Frame", frame)
    if len(parsed.sealed) < TAG_LEN or len(iv_key) != 8 or len(key) != 16:
        raise GoveeCryptoError("invalid_frame")
    ctr = parsed.counter.to_bytes(4, "big")
    try:
        plain = AESGCM(key).decrypt(iv_key + ctr, parsed.sealed, ctr)
    except InvalidTag, ValueError:
        raise GoveeCryptoError("frame_authentication_failed") from None
    return parsed.counter, plain
