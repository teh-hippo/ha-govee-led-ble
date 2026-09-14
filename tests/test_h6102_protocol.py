"""H6102 protocol selection tests."""

import pytest

from custom_components.ha_govee_led_ble.firmware_version import FirmwareVersion
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_brightness,
    build_h6102_extended_rgb,
    build_power,
    parse_command_result,
)
from custom_components.ha_govee_led_ble.h6102_protocol import (
    H6102RgbVariant,
    classify_h6102_rgb,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.03.00", H6102RgbVariant.LEGACY),
        ("1.03.01", H6102RgbVariant.EXTENDED),
        ("1.03.02", H6102RgbVariant.EXTENDED),
        ("1.3", H6102RgbVariant.LEGACY),
        ("1.3.1", H6102RgbVariant.EXTENDED),
        ("1.2.9999", H6102RgbVariant.LEGACY),
        ("1.100.0", H6102RgbVariant.EXTENDED),
        ("001.003.000", H6102RgbVariant.LEGACY),
        ("001.003.001", H6102RgbVariant.EXTENDED),
    ],
)
def test_classifies_firmware_versions(value: str, expected: H6102RgbVariant) -> None:
    version = FirmwareVersion.parse(value)
    assert version is not None
    assert classify_h6102_rgb(version) is expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        ".1",
        "1.",
        "1..3",
        "+1.03.01",
        "1. 03.01",
        "1.03.x",
    ],
)
def test_missing_and_malformed_versions_fail_closed(value: str | None) -> None:
    assert classify_h6102_rgb(FirmwareVersion.parse(value)) is None


@pytest.mark.parametrize(
    ("packet", "opcode"),
    [
        (build_power(True, "H6102"), "power"),
        (build_brightness(50, "H6102"), "brightness"),
        (build_h6102_extended_rgb(0x7FFF, 32, 64, 96), "mode"),
    ],
)
def test_captured_command_grammar_round_trips(packet: bytes, opcode: str) -> None:
    result = parse_command_result(packet, "H6102")

    assert result.rejection is None
    assert result.parser == "h6102_command_write"
    assert result.parsed is not None
    assert result.parsed.opcode.name == opcode


def test_uncaptured_command_values_fail_closed() -> None:
    with pytest.raises(ValueError, match="brightness"):
        build_brightness(0, "H6102")
    with pytest.raises(ValueError, match="region mask"):
        build_h6102_extended_rgb(0, 1, 2, 3)
