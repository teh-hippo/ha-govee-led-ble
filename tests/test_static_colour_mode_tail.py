"""The static colour-mode reply carries the device's colour temperature.

`cm_static` validated every byte after `sub` as zero. An H66A0 in colour-temperature mode
answers `aa 05 15 00 0f a0 00...`, so the check failed, the whole frame was rejected, and the
colour-mode domain was never observed. The device then never completed a state refresh and its
config entry sat in setup_retry reporting "unreachable at setup" -- with power, brightness,
firmware and hardware all answering normally on the same connection.

The bytes are the temperature in Kelvin, big-endian. Measured on two devices against arbitrary
requested values, matching exactly each time. Zero means the device is not reporting one: it
reads zero in RGB mode everywhere, and zero on an H61F5 even in colour-temperature mode.
"""

from __future__ import annotations

import pytest

from custom_components.ha_govee_led_ble.coordinator_status import decode_status_frame_result


def _frame(body: str) -> bytes:
    raw = bytes.fromhex(body)
    padded = bytearray(raw + bytes(19 - len(raw)))
    checksum = 0
    for byte in padded[:19]:
        checksum ^= byte
    return bytes(padded + bytes([checksum]))


@pytest.mark.parametrize(
    ("body", "kelvin"),
    [
        ("aa0515000fa0", 4000),  # H66A0 and H1A42, asked for 4000 K
        ("aa0515001964", 6500),  # asked for 6500 K
        ("aa0515000c33", 3123),  # an arbitrary value, to rule out a lookup table
        ("aa051500", 0),  # RGB mode, and an H61F5 in colour-temperature mode
    ],
)
def test_static_colour_mode_reports_its_colour_temperature(body: str, kelvin: int) -> None:
    parsed = decode_status_frame_result(_frame(body), "H617A").parsed
    assert parsed is not None, f"{body} was rejected"
    assert parsed.generated.body.mode_body.colour_temperature_kelvin == kelvin


def test_the_zero_check_would_have_rejected_a_reported_temperature() -> None:
    """The regression in one line: a device reporting 4000 K had its whole frame thrown away."""
    parsed = decode_status_frame_result(_frame("aa0515000fa0"), "H617A").parsed
    assert parsed is not None
    assert parsed.generated.body.mode_body.sub == 0
    assert bytes(parsed.generated.body.mode_body.opaque) == bytes(13)
