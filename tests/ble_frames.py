"""Checksummed BLE frame builders shared by protocol tests."""

from collections.abc import Iterable

from custom_components.ha_govee_led_ble.transport import xor_checksum


def frame(prefix: str) -> bytes:
    """Pad a hex prefix to a checksummed 20-byte frame."""
    body = bytes.fromhex(prefix).ljust(19, b"\0")
    assert len(body) == 19
    return body + bytes((xor_checksum(body),))


def status_frame(domain: int, body: Iterable[int]) -> bytes:
    """Build a checksummed status reply for one read domain."""
    return frame(bytes((0xAA, domain, *body)).hex())
