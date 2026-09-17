"""H6102 RGB selection from independent Pact and revision evidence."""

from enum import StrEnum

from .firmware_version import FirmwareVersion

H6102_PACTS = {"1/1": (1, 1), "1/2": (1, 2), "10/1": (10, 1), "10/2": (10, 2)}


class H6102RgbVariant(StrEnum):
    """Known H6102 RGB encodings; unknown context authorizes neither."""

    LEGACY = "legacy"
    EXTENDED = "extended"


def classify_h6102_rgb(
    version: FirmwareVersion | None,
    *,
    hardware: FirmwareVersion | None = None,
    pact_type: int | None = None,
    pact_code: int | None = None,
) -> H6102RgbVariant | None:
    """The APK's 1.03.01 UI migration is not a wire-encoding boundary."""
    if pact_type == 10 and pact_code in (1, 2):
        return H6102RgbVariant.EXTENDED
    if pact_type == 1 and pact_code in (1, 2) and version is not None and hardware is not None:
        if hardware >= FirmwareVersion((1, 0, 3)) and version >= FirmwareVersion((1, 6)):
            return H6102RgbVariant.EXTENDED
        return H6102RgbVariant.LEGACY
    return None
