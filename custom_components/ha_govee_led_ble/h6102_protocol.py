"""H6102 firmware-dependent protocol selection."""

from enum import StrEnum

from .firmware_version import FirmwareVersion


class H6102RgbVariant(StrEnum):
    """H6102 whole-device RGB command variants."""

    LEGACY = "legacy"
    EXTENDED = "extended"


_parsed_extended_rgb_min_version = FirmwareVersion.parse("1.03.01")
assert _parsed_extended_rgb_min_version is not None
_EXTENDED_RGB_MIN_VERSION: FirmwareVersion = _parsed_extended_rgb_min_version


def classify_h6102_rgb(version: FirmwareVersion | None) -> H6102RgbVariant | None:
    """Select the RGB variant for a parsed firmware version."""
    if version is None:
        return None
    return H6102RgbVariant.LEGACY if version < _EXTENDED_RGB_MIN_VERSION else H6102RgbVariant.EXTENDED
