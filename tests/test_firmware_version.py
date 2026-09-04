"""Dotted-decimal firmware version tests."""

import pytest

from custom_components.ha_govee_led_ble.firmware_version import FirmwareVersion


def _version(value: str) -> FirmwareVersion:
    version = FirmwareVersion.parse(value)
    assert version is not None
    return version


def test_versions_compare_numerically_with_zero_padding() -> None:
    assert _version("1.03.00") == _version("1.3")
    assert _version("1.03.00") < _version("1.03.01")
    assert _version("1.3") < _version("1.3.1")
    assert _version("1.03.01") == _version("1.3.1")
    assert _version("1.10.00") > _version("1.03.01")
    assert _version("01.003.000") == _version("1.3")


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        ".1",
        "1..3",
        "+1.3",
        "1. 3",
        " 1.3",
        "1.three",
        "1.٣",
    ],
)
def test_invalid_versions_fail_closed(value: str | None) -> None:
    assert FirmwareVersion.parse(value) is None
