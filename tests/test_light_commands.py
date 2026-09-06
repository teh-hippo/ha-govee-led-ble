"""Semantic light-command tests."""

import pytest

from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    ProtocolParseRejection,
    build_brightness,
    build_brightness_query,
    build_colour_mode_query,
    build_colour_temperature,
    build_firmware_query,
    build_h6102_extended_rgb,
    build_hardware_query,
    build_music_mode,
    build_power,
    build_power_query,
    build_segment_colour,
    build_segment_query,
    parse_a3_effect_envelope,
    parse_command,
    parse_command_result,
    parse_status,
)
from custom_components.ha_govee_led_ble.generated_protocol_adapter import (
    build_segment_brightness as build_segment_brightness_mask,
)
from custom_components.ha_govee_led_ble.h6102_protocol import H6102RgbVariant
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


@pytest.mark.parametrize("model", ["H617A", "H617E", "H6076", "H6199"])
def test_power_and_brightness_remain_byte_identical(model: str) -> None:
    assert build_power(True, model) == H("3301010000000000000000000000000000000033")
    assert build_power(False, model) == H("3301000000000000000000000000000000000032")
    assert build_brightness(42, model) == H("33042a000000000000000000000000000000001d")
    assert build_brightness(200, model) == H("3304640000000000000000000000000000000053")


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (False, "3301000000000000000000000000000000000032"),
        (True, "3301010000000000000000000000000000000033"),
    ],
)
def test_h6102_power_uses_its_registered_root(on: bool, expected: str) -> None:
    frame = build_power(on, "H6102")
    parsed = parse_command(frame, "H6102")

    assert frame == H(expected)
    assert parsed is not None and parsed.__class__.__name__ == "H6102CommandWrite"
    assert parsed.opcode.name == "power"
    assert parsed.body.value == int(on)


@pytest.mark.parametrize(
    ("percent", "expected"),
    [
        (1, "3304010000000000000000000000000000000036"),
        (50, "3304320000000000000000000000000000000005"),
        (75, "33044b000000000000000000000000000000007c"),
        (100, "3304640000000000000000000000000000000053"),
    ],
)
def test_h6102_brightness_uses_its_registered_root(percent: int, expected: str) -> None:
    frame = build_brightness(percent, "H6102")
    parsed = parse_command(frame, "H6102")

    assert frame == H(expected)
    assert parsed is not None and parsed.__class__.__name__ == "H6102CommandWrite"
    assert parsed.opcode.name == "brightness"
    assert parsed.body.percent == percent


@pytest.mark.parametrize("percent", [0, 101, 255])
def test_h6102_brightness_rejects_uncaptured_values(percent: int) -> None:
    with pytest.raises(ValueError, match="1 to 100"):
        build_brightness(percent, "H6102")


def test_h6102_parse_command_result_exposes_registered_parser() -> None:
    result = parse_command_result(build_power(True, "H6102"), "H6102")

    assert result.parser == "h6102_command_write"
    assert result.rejection is None
    assert result.parsed is not None and result.parsed.opcode.name == "power"


def test_command_rejections_expose_stable_reasons_and_fail_closed() -> None:
    frame = build_power(True, "H6102")
    assert parse_command_result(frame[:-1], "H6102").rejection is ProtocolParseRejection.INVALID_LENGTH

    bad_checksum = frame[:-1] + bytes([frame[-1] ^ 0x01])
    assert parse_command_result(bad_checksum, "H6102").rejection is ProtocolParseRejection.INVALID_CHECKSUM

    unsupported = parse_command_result(frame, "H9999")
    assert unsupported.parser is None
    assert unsupported.rejection is ProtocolParseRejection.UNSUPPORTED_MODEL

    invalid_shape = bytearray(build_brightness(100))
    invalid_shape[2] = 101
    invalid_shape[-1] = xor_checksum(invalid_shape[:-1])
    rejected = parse_command_result(bytes(invalid_shape))
    assert rejected.parser == "command_write"
    assert rejected.rejection is ProtocolParseRejection.SCHEMA_REJECTED


@pytest.mark.parametrize(
    ("mask", "rgb", "expected"),
    [
        (0x7FFF, (32, 64, 96), "330515012040600000000000ff7f0000000000a2"),
        (0x5961, (255, 0, 0), "33051501ff0000000000000061590000000000e5"),
    ],
)
def test_h6102_extended_rgb_builder(
    mask: int,
    rgb: tuple[int, int, int],
    expected: str,
) -> None:
    frame = build_h6102_extended_rgb(mask, *rgb)
    parsed = parse_command(frame, "H6102")

    assert frame == H(expected)
    assert parsed is not None and parsed.opcode.name == "mode"
    assert parsed.body.selector == b"\x15"
    assert parsed.body.operation == b"\x01"
    assert (parsed.body.rgb_direct.red, parsed.body.rgb_direct.green, parsed.body.rgb_direct.blue) == rgb
    assert parsed.body.mask.bits == mask


@pytest.mark.parametrize(
    ("rgb", "expected"),
    [
        ((32, 64, 96), "330515012040600000000000ff7f0000000000a2"),
        ((0, 0, 0), "330515010000000000000000ff7f0000000000a2"),
    ],
)
def test_h6102_semantic_rgb_builder_requires_extended_variant(
    rgb: tuple[int, int, int],
    expected: str,
) -> None:
    frame = build_color_rgb(*rgb, "H6102", h6102_variant=H6102RgbVariant.EXTENDED)
    parsed = parse_static_write(frame, "H6102")

    assert frame == H(expected)
    assert parsed is not None
    assert parsed.whole_strip
    assert parsed.rgb == rgb
    assert parsed.kelvin is None


@pytest.mark.parametrize("variant", [None, H6102RgbVariant.LEGACY])
def test_h6102_semantic_rgb_builder_rejects_unenabled_variants(
    variant: H6102RgbVariant | None,
) -> None:
    with pytest.raises(ValueError, match="requires the extended variant"):
        build_color_rgb(255, 0, 0, "H6102", h6102_variant=variant)


@pytest.mark.parametrize("mask", [0, 0x8000, 0x10000])
def test_h6102_extended_rgb_requires_nonzero_15_bit_mask(mask: int) -> None:
    with pytest.raises(ValueError, match="0x0001 to 0x7fff"):
        build_h6102_extended_rgb(mask, 255, 0, 0)


def test_h6102_absent_command_bodies_fail_closed() -> None:
    for frame in (
        H("3305130663000000000000000000000000000040"),
        H("3305040400000000000000000000000000000036"),
        H("33050a000000000000000000000000000000003c"),
    ):
        assert parse_command(frame, "H6102") is None

    with pytest.raises(ValueError, match="static-colour grammar"):
        build_segment_colour(0x7FFF, 255, 0, 0, "H6102")
    with pytest.raises(ValueError, match="segment-brightness grammar"):
        build_segment_brightness_mask(0x7FFF, 50, "H6102")
    with pytest.raises(ValueError, match="colour-temperature grammar"):
        build_colour_temperature(4000, (255, 255, 255), 0x7FFF, "H6102")
    with pytest.raises(ValueError, match="music grammar"):
        build_music_mode(0x03, 50, None, False, "H6102")


def test_h6102_status_paths_fail_closed() -> None:
    assert parse_status(H("aaa50164ff880d64ff880d64ff880d0000000010"), "H6102") is None

    for builder in (
        build_power_query,
        build_brightness_query,
        build_colour_mode_query,
        build_firmware_query,
        build_hardware_query,
    ):
        with pytest.raises(ValueError, match="status-query grammar"):
            builder("H6102")
    with pytest.raises(ValueError, match="segment-query grammar"):
        build_segment_query(1, "H6102")


@pytest.mark.parametrize("body_type", [0x01, 0x02, 0x03, 0x04])
def test_h6102_a3_paths_fail_closed(body_type: int) -> None:
    envelope = bytes([0x01, 0x01, body_type]) + bytes(14)

    with pytest.raises(ValueError, match="H6102 has no generated A3 effect grammar"):
        parse_a3_effect_envelope(envelope, "H6102")


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


def test_segment_numbering_and_masks() -> None:
    assert segments_to_mask([1]) == 0x0001
    assert segments_to_mask([3]) == 0x0004
    assert segments_to_mask([15]) == 0x4000
    assert segments_to_mask(ALL_SEGMENTS) == ALL_SEGMENTS_MASK
    for invalid in ([], [0], [16], [-1], [1, 16]):
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
