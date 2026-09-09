"""Semantic light-command tests."""

from dataclasses import replace

import pytest

from custom_components.ha_govee_led_ble.const import MODEL_PROFILES
from custom_components.ha_govee_led_ble.generated_protocol_adapter import build_brightness, build_power
from custom_components.ha_govee_led_ble.light_commands import (
    ALL_SEGMENTS,
    ALL_SEGMENTS_MASK,
    build_color_rgb,
    build_color_temp,
    build_segment_brightness,
    build_segment_color,
    build_segment_paint,
    build_white_brightness,
    kelvin_to_rgb,
    parse_static_write,
    segments_to_mask,
)
from custom_components.ha_govee_led_ble.transport import xor_checksum

H = bytes.fromhex


def _assert_valid(frame: bytes) -> None:
    assert len(frame) == 20
    assert xor_checksum(frame[:19]) == frame[19]


@pytest.mark.parametrize("model", ["H617A", "H6199"])
def test_power_and_brightness_remain_byte_identical(model: str) -> None:
    assert build_power(True, model) == H("3301010000000000000000000000000000000033")
    assert build_power(False, model) == H("3301000000000000000000000000000000000032")
    assert build_brightness(200, model)[2] == 100


def test_whole_strip_colour_temperature_and_brightness() -> None:
    assert build_color_rgb(10, 20, 30) == H("330515010a141e0000000000ff7f0000000000a2")
    assert build_white_brightness(50) == H("3305150232ff7f00000000000000000000000093")
    temperature = build_color_temp(4000)
    assert temperature[7:9] == (4000).to_bytes(2, "big")
    assert tuple(temperature[9:12]) == kelvin_to_rgb(4000)
    assert build_color_temp(1000)[7:9] == (2000).to_bytes(2, "big")
    assert build_color_temp(12000)[7:9] == (9000).to_bytes(2, "big")


def test_h6076_uses_its_whole_device_mask_and_kelvin_range() -> None:
    colour = build_color_rgb(10, 20, 30, "H6076")
    assert colour[12:14] == b"\x7f\x00"
    parsed = parse_static_write(colour, "H6076")
    assert parsed is not None and parsed.whole_strip
    assert build_color_temp(2000, "H6076")[7:9] == (2700).to_bytes(2, "big")
    assert build_color_temp(9000, "H6076")[7:9] == (6500).to_bytes(2, "big")
    assert build_color_temp(4000, "H6076")[12:14] == b"\x7f\x00"
    assert build_white_brightness(50, "H6076") == H("33051502327f000000000000000000000000006c")


def test_segment_numbering_and_masks() -> None:
    assert segments_to_mask([1]) == 0x0001
    assert segments_to_mask([3]) == 0x0004
    assert segments_to_mask([15]) == 0x4000
    assert segments_to_mask(ALL_SEGMENTS) == ALL_SEGMENTS_MASK
    assert segments_to_mask(iter([1, 1, 3])) == 0x0005
    for invalid in ([], [0], [16], [-1], [1, 16], [1, True], [1, 1.0], [1.5], ["1"]):
        with pytest.raises(ValueError):
            segments_to_mask(invalid)


def test_segment_commands_and_paint_order() -> None:
    colour = build_segment_color([1, 5, 9], 1, 2, 3)
    assert colour[12:14] == bytes([0x11, 0x01])
    brightness = build_segment_brightness([15], 50)
    assert brightness[:7] == bytes([0x33, 0x05, 0x15, 0x02, 50, 0, 0x40])
    groups = [([1, 2], (255, 0, 0)), ([3], (0, 0, 255))]
    assert build_segment_paint(groups) == [
        build_segment_color([1, 2], 255, 0, 0),
        build_segment_color([3], 0, 0, 255),
    ]
    _assert_valid(colour)
    _assert_valid(brightness)


@pytest.mark.parametrize("count", [5, 14])
def test_segment_builders_validate_effective_profile(count):
    profile = replace(MODEL_PROFILES["H617A"], segment_count=count)
    for selected in ([count], [count + 1]):
        builders = (
            lambda selected=selected: build_segment_color(iter(selected), 1, 2, 3, profile=profile),
            lambda selected=selected: build_segment_brightness(iter(selected), 50, profile=profile),
            lambda selected=selected: build_segment_paint(iter([(iter(selected), (1, 2, 3))]), profile=profile)[0],
        )
        for build in builders:
            if selected == [count]:
                parsed = parse_static_write(build())
                assert parsed is not None and parsed.segment_mask == 1 << (count - 1)
            else:
                with pytest.raises(ValueError, match=f"1..{count}"):
                    build()


@pytest.mark.parametrize("model", ["H6076", "H617A"])
def test_segment_builders_require_segment_capability(model):
    profile = replace(MODEL_PROFILES[model], supports_segment_writes=False)
    for build, args in (
        (build_segment_color, ([1], 1, 2, 3)),
        (build_segment_brightness, ([1], 50)),
        (build_segment_paint, ([([1], (1, 2, 3))],)),
    ):
        with pytest.raises(ValueError, match="per-segment control"):
            build(*args, model=model, profile=profile)
        if model == "H6076":
            with pytest.raises(ValueError, match="per-segment control"):
                build(*args, model=model)
    with pytest.raises(ValueError, match="non-empty"):
        build_segment_paint(iter([]))


@pytest.mark.parametrize("model", ["H617A", "H6199"])
def test_static_write_semantics_round_trip(model: str) -> None:
    rgb = parse_static_write(build_segment_color([3], 10, 20, 30, model), model)
    assert rgb is not None and rgb.rgb == (10, 20, 30) and rgb.segment_mask == 0x0004
    black = parse_static_write(build_color_rgb(0, 0, 0, model), model)
    assert black is not None and black.rgb == (0, 0, 0) and black.kelvin is None
    temperature = parse_static_write(build_color_temp(3600, model), model)
    assert temperature is not None and temperature.kelvin == 3600
    assert temperature.kelvin_companion_rgb == kelvin_to_rgb(3600)
    level = parse_static_write(build_white_brightness(80, model), model)
    assert level is not None and level.brightness_pct == 80 and level.whole_strip
