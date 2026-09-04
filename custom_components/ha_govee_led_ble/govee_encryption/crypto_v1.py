"""Primitives for the Govee **v1** BLE encryption scheme (``0xE7 0x01``/``0xE7 0x02``).

Pure functions -- no Bluetooth, no Home Assistant, no I/O. :mod:`.crypto` holds the v2
(AES-GCM) scheme; this is the older generation that sits beside it.

An H61F5 exposes no ``2b12`` marker but silently ignores plaintext frames, so version 1
must be attempted before treating an unmarked device as plaintext.

Two properties are worth knowing before reading the code:

* The transform is **length-preserving**. A 20-byte command stays 20 bytes on the wire,
  where v2 seals the same command into 40. That is the cheapest way to tell the two apart
  in a capture.
* The RC4 tail is **restarted from the key for every frame**, so the keystream covering
  bytes 16-19 is a constant for a given key. Every zero-padded frame therefore shows the
  same three bytes at 16..18. That is a real weakness, and it is also how this scheme was
  first spotted in a capture before the key was known.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .crypto import GoveeCryptoError

# Protocol-wide communication key. It is shared across devices, not device-specific.
KEY_COMMUNICATION = bytes.fromhex("4D616B696E674C696665536D61727465")

MAGIC = 0xE7
CMD_SESSION_KEY = 0x01
CMD_CONFIRM = 0x02
FRAME_LEN = 20
SESSION_KEY_LEN = 16
ENCRYPTION_VERSION_V1 = 1


def _rc4(data: bytes, key: bytes) -> bytes:
    """``Safe.g()`` -- textbook RC4, keyed afresh on every call."""
    box = list(range(256))
    j = 0
    for i in range(256):  # Safe.f(), the key schedule
        j = (j + box[i] + key[i % len(key)]) % 256
        box[i], box[j] = box[j], box[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) & 0xFF
        j = (box[i] + j) & 0xFF
        box[i], box[j] = box[j], box[i]
        out.append(box[(box[i] + box[j]) & 0xFF] ^ byte)
    return bytes(out)


def _aes_ecb(block: bytes, key: bytes, *, encrypt: bool) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())  # noqa: S305 -- the app's own choice
    ctx = cipher.encryptor() if encrypt else cipher.decryptor()
    return ctx.update(block) + ctx.finalize()


def _transform(data: bytes, key: bytes, *, encrypt: bool) -> bytes:
    """``Safe.d()`` / ``Safe.b()``: whole blocks through AES-ECB, the remainder through RC4."""
    if len(key) != 16:
        raise GoveeCryptoError(f"v1 key must be 16 bytes, got {len(key)}")
    whole, remainder = divmod(len(data), 16)
    out = bytearray()
    for index in range(whole):
        out += _aes_ecb(data[index * 16 : (index + 1) * 16], key, encrypt=encrypt)
    if remainder:
        out += _rc4(data[whole * 16 :], key)
    return bytes(out)


def encrypt(packet: bytes, key: bytes) -> bytes:
    return _transform(packet, key, encrypt=True)


def decrypt(frame: bytes, key: bytes) -> bytes:
    return _transform(frame, key, encrypt=False)


def xor_checksum(frame: bytes | bytearray) -> int:
    """The protocol's own check byte: XOR of bytes 0..18.

    Accepts a bytearray so a frame can be checksummed while it is still being built.
    """
    check = 0
    for byte in frame[:19]:
        check ^= byte
    return check


def checksum_ok(frame: bytes) -> bool:
    return len(frame) == FRAME_LEN and xor_checksum(frame) == frame[19]


def _build(command: int, *, randomise: bool) -> bytes:
    """``Controller4Aes.a()`` -- ``[E7][cmd][pad to 18][checksum]``.

    The app fills the middle with ``Random.nextInt`` rather than zeros. ``randomise=False``
    exists only so tests can pin an exact frame; the device does not care either way, and
    nothing about the scheme depends on the padding being unpredictable.
    """
    frame = bytearray(FRAME_LEN)
    frame[0] = MAGIC
    frame[1] = command
    if randomise:
        frame[2:19] = os.urandom(17)
    frame[19] = xor_checksum(frame)
    return bytes(frame)


def build_session_request(*, randomise: bool = True) -> bytes:
    """``Controller4Aes.e()`` -- the ``0xE7 0x01`` request, sealed under KEY_COMMUNICATION."""
    return encrypt(_build(CMD_SESSION_KEY, randomise=randomise), KEY_COMMUNICATION)


def build_confirm(*, randomise: bool = True) -> bytes:
    """``Controller4Aes.f()`` -- the ``0xE7 0x02`` confirm, sealed under KEY_COMMUNICATION."""
    return encrypt(_build(CMD_CONFIRM, randomise=randomise), KEY_COMMUNICATION)


def parse_negotiation_frame(frame: bytes) -> tuple[int, bytes] | None:
    """Decrypt a negotiation frame under KEY_COMMUNICATION.

    Returns ``(command, plaintext)`` for a well-formed ``0xE7`` frame, else ``None``. Used
    while negotiating, when every frame on the wire is still under the app-global key.

    ``None`` covers a frame that is simply not ours -- a plaintext device answering a probe,
    or a v1 device already past its handshake -- so callers treat it as "not a negotiation
    frame" rather than as an error.
    """
    if len(frame) != FRAME_LEN:
        return None
    try:
        plain = decrypt(frame, KEY_COMMUNICATION)
    except Exception:  # a malformed frame is data, not a crash
        return None
    if plain[0] != MAGIC or not checksum_ok(plain):
        return None
    return plain[1], plain


def parse_session_key(plaintext: bytes) -> bytes:
    """``Controller4Aes.g()`` -- the session key is ``plaintext[2:18]``."""
    if plaintext[0] != MAGIC or plaintext[1] != CMD_SESSION_KEY:
        raise GoveeCryptoError(f"not a v1 session-key reply: {plaintext[:2].hex()}")
    return plaintext[2 : 2 + SESSION_KEY_LEN]
