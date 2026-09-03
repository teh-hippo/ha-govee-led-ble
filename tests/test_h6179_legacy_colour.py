"""Tests for the dormant H6179 legacy colour variant."""

import pytest

from custom_components.ha_govee_led_ble.h6179_legacy_colour import H6179_LEGACY_COLOUR_VARIANT
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex


def test_legacy_variant_is_explicit_and_unambiguous() -> None:
    assert H6179_LEGACY_COLOUR_VARIANT.name == "h6179-legacy-colour-33-05-02"


@pytest.mark.parametrize(
    ("rgb", "expected"),
    [
        ((0, 0, 0), "3305020000000000000000000000000000000034"),
        ((255, 0, 0), "330502ff000000000000000000000000000000cb"),
        ((0, 255, 0), "33050200ff0000000000000000000000000000cb"),
        ((0, 0, 255), "3305020000ff00000000000000000000000000cb"),
        ((255, 0, 128), "330502ff0080000000000000000000000000004b"),
    ],
)
def test_legacy_colour_vectors(rgb: tuple[int, int, int], expected: str) -> None:
    packet = H6179_LEGACY_COLOUR_VARIANT.build_colour(*rgb)

    assert packet == H(expected)
    assert len(packet) == 20
    assert packet[6:19] == bytes(13)
    assert packet[19] == xor_checksum(packet[:19])


@pytest.mark.parametrize(
    ("raw_level", "expected"),
    [
        (0, "3304000000000000000000000000000000000037"),
        (127, "33047f0000000000000000000000000000000048"),
        (254, "3304fe00000000000000000000000000000000c9"),
    ],
)
def test_legacy_brightness_vectors(raw_level: int, expected: str) -> None:
    assert H6179_LEGACY_COLOUR_VARIANT.build_brightness(raw_level) == H(expected)


@pytest.mark.parametrize("rgb", [(-1, 0, 0), (0, 256, 0), (0, 0, 1.5)])
def test_legacy_colour_rejects_invalid_channels(rgb: tuple[int, int, int]) -> None:
    with pytest.raises(ValueError, match="integer from 0 to 255"):
        H6179_LEGACY_COLOUR_VARIANT.build_colour(*rgb)


@pytest.mark.parametrize("raw_level", [-1, 256])
def test_legacy_brightness_rejects_out_of_range_raw_levels(raw_level: int) -> None:
    with pytest.raises(ValueError, match="integer from 0 to 255"):
        H6179_LEGACY_COLOUR_VARIANT.build_brightness(raw_level)
