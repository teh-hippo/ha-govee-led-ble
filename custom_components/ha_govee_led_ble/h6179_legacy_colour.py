"""Dormant H6179 fallback for the legacy ``33 05 02`` colour command."""

from dataclasses import dataclass

from .transport import xor_checksum

_FRAME_DATA_LENGTH = 19


def _frame(command: bytes) -> bytes:
    data = command.ljust(_FRAME_DATA_LENGTH, b"\x00")
    return data + bytes((xor_checksum(data),))


def _byte(value: int, name: str) -> int:
    if not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be an integer from 0 to 255")
    return value


@dataclass(frozen=True, slots=True)
class H6179LegacyColourVariant:
    """Explicit, unregistered H6179 legacy command variant."""

    name: str = "h6179-legacy-colour-33-05-02"

    def build_colour(self, red: int, green: int, blue: int) -> bytes:
        """Build the legacy whole-device RGB command."""
        return _frame(bytes((0x33, 0x05, 0x02, _byte(red, "red"), _byte(green, "green"), _byte(blue, "blue"))))

    def build_brightness(self, raw_level: int) -> bytes:
        """Build the evidenced H6179 command carrying an unscaled brightness byte."""
        return _frame(bytes((0x33, 0x04, _byte(raw_level, "raw brightness"))))


H6179_LEGACY_COLOUR_VARIANT = H6179LegacyColourVariant()
