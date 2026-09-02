"""Semantic colour, temperature, segment and brightness commands."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .const import get_profile
from .generated_protocol_adapter import (
    build_colour_temperature,
    build_segment_colour,
    parse_command,
)
from .generated_protocol_adapter import (
    build_segment_brightness as build_segment_brightness_mask,
)

SEGMENT_COUNT = 15
ALL_SEGMENTS: tuple[int, ...] = tuple(range(1, SEGMENT_COUNT + 1))
ALL_SEGMENTS_MASK = 0x7FFF

type SegmentColorGroup = tuple[Iterable[int], tuple[int, int, int]]

_H6125_CCT_COMPANION_RGB = (
    (255, 141, 11),
    (255, 146, 29),
    (255, 152, 41),
    (255, 157, 51),
    (255, 162, 60),
    (255, 166, 69),
    (255, 170, 77),
    (255, 174, 84),
    (255, 178, 91),
    (255, 182, 98),
    (255, 185, 105),
    (255, 189, 111),
    (255, 192, 118),
    (255, 195, 124),
    (255, 198, 130),
    (255, 201, 135),
    (255, 203, 141),
    (255, 206, 146),
    (255, 208, 151),
    (255, 211, 156),
    (255, 213, 161),
    (255, 215, 166),
    (255, 217, 171),
    (255, 219, 175),
    (255, 221, 180),
    (255, 223, 184),
    (255, 225, 188),
    (255, 226, 192),
    (255, 228, 196),
    (255, 229, 200),
    (255, 231, 204),
    (255, 232, 208),
    (255, 234, 211),
    (255, 235, 215),
    (255, 237, 218),
    (255, 238, 222),
    (255, 239, 225),
    (255, 240, 228),
    (255, 241, 231),
    (255, 243, 234),
    (255, 244, 237),
    (255, 245, 240),
    (255, 246, 243),
    (255, 247, 247),
    (255, 248, 248),
    (255, 249, 251),
    (255, 249, 253),
    (254, 250, 255),
    (252, 248, 255),
    (250, 247, 255),
    (247, 245, 255),
    (245, 244, 255),
    (243, 243, 255),
    (241, 241, 255),
    (239, 240, 255),
    (238, 239, 255),
    (236, 238, 255),
    (234, 237, 255),
    (233, 236, 255),
    (231, 234, 255),
    (229, 233, 255),
    (228, 233, 255),
    (227, 232, 255),
    (225, 231, 255),
    (224, 230, 255),
    (223, 229, 255),
    (221, 228, 255),
    (220, 227, 255),
    (219, 226, 255),
    (218, 226, 255),
    (217, 225, 255),
)


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def segments_to_mask(segments: Iterable[int]) -> int:
    """Map one-based segment numbers to the device's 15-bit segment mask."""
    selected = set(segments)
    if not selected:
        raise ValueError("no segments selected")
    mask = 0
    for segment in selected:
        if not 1 <= segment <= SEGMENT_COUNT:
            raise ValueError(f"segment {segment} out of range 1..{SEGMENT_COUNT}")
        mask |= 1 << (segment - 1)
    return mask


def build_segment_color(
    segments: Iterable[int],
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
) -> bytes:
    return build_segment_colour(segments_to_mask(segments), red, green, blue, model)


def build_segment_brightness(
    segments: Iterable[int],
    percent: int,
    model: str = "H617A",
) -> bytes:
    return build_segment_brightness_mask(segments_to_mask(segments), percent, model)


def build_segment_paint(
    groups: Iterable[SegmentColorGroup],
    model: str = "H617A",
) -> list[bytes]:
    """Build one packet for each group because distinct colours require distinct writes."""
    return [build_segment_color(segments, red, green, blue, model) for segments, (red, green, blue) in groups]


def build_color_rgb(red: int, green: int, blue: int, model: str = "H617A") -> bytes:
    return build_segment_colour(get_profile(model).whole_device_mask, red, green, blue, model)


def normalise_kelvin(kelvin: int, model: str = "H617A") -> int:
    profile = get_profile(model)
    value = _clamp(kelvin, profile.min_color_temp_kelvin, profile.max_color_temp_kelvin)
    return value // 100 * 100 if model == "H6125" else value


def kelvin_to_rgb(kelvin: int, model: str = "H617A") -> tuple[int, int, int]:
    if model == "H6125":
        value = normalise_kelvin(kelvin, model)
        return _H6125_CCT_COMPANION_RGB[(value - 2000) // 100]
    temp = _clamp(kelvin, 1000, 10000) / 100.0
    red = 255.0 if temp <= 66 else _clamp(int(329.698727446 * ((temp - 60) ** -0.1332047592)), 0, 255)
    green = (
        99.4708025861 * math.log(temp) - 161.1195681661
        if temp <= 66
        else 288.1221695283 * ((temp - 60) ** -0.0755148492)
    )
    blue = 255.0 if temp >= 66 else 0.0 if temp <= 19 else 138.5177312231 * math.log(temp - 10) - 305.0447927307
    return int(red), _clamp(int(green), 0, 255), _clamp(int(blue), 0, 255)


def build_color_temp(kelvin: int, model: str = "H617A") -> bytes:
    profile = get_profile(model)
    value = normalise_kelvin(kelvin, model)
    return build_colour_temperature(value, kelvin_to_rgb(value, model), profile.whole_device_mask, model)


def build_white_brightness(percent: int, model: str = "H617A") -> bytes:
    return build_segment_brightness(ALL_SEGMENTS, percent, model)


@dataclass(frozen=True)
class ParsedStaticWrite:
    """Static-command fields used by optimistic state and the BLE simulator."""

    operation: int
    segment_mask: int
    whole_device_mask: int = ALL_SEGMENTS_MASK
    rgb: tuple[int, int, int] | None = None
    kelvin: int | None = None
    kelvin_companion_rgb: tuple[int, int, int] | None = None
    brightness_pct: int | None = None

    @property
    def whole_strip(self) -> bool:
        return self.segment_mask == self.whole_device_mask


def parse_static_write(packet: bytes, model: str = "H617A") -> ParsedStaticWrite | None:
    """Convert a generated static command into optimistic semantic state."""
    generated = parse_command(packet, model)
    if generated is None:
        return None
    whole_device_mask = get_profile(model).whole_device_mask
    if model == "H6199":
        if generated.opcode.name != "mode" or getattr(generated.body.sub_mode, "name", None) != "static_colour":
            return None
        detail = generated.body.detail
        operation = int(detail.operation)
        if detail.operation.name == "colour":
            rgb = (int(detail.red), int(detail.green), int(detail.blue))
            kelvin = int(detail.kelvin)
            if kelvin and rgb == (0, 0, 0):
                preview = detail.preview
                return ParsedStaticWrite(
                    operation=operation,
                    segment_mask=int(detail.segment_mask),
                    whole_device_mask=whole_device_mask,
                    kelvin=kelvin,
                    kelvin_companion_rgb=(int(preview.red), int(preview.green), int(preview.blue)),
                )
            return ParsedStaticWrite(
                operation=operation,
                segment_mask=int(detail.segment_mask),
                whole_device_mask=whole_device_mask,
                rgb=rgb,
            )
        if detail.operation.name == "brightness":
            return ParsedStaticWrite(
                operation=operation,
                segment_mask=int(detail.brightness_segment_mask),
                whole_device_mask=whole_device_mask,
                brightness_pct=int(detail.brightness_percent),
            )
        return None
    if generated.opcode.name != "multi" or getattr(generated.body.sub, "name", None) != "static":
        return None
    detail = generated.body.sub_body
    operation = int(detail.static_sub)
    body = detail.static_body
    if hasattr(body, "rgb_direct"):
        rgb = (int(body.rgb_direct.red), int(body.rgb_direct.green), int(body.rgb_direct.blue))
        kelvin = int(body.kelvin)
        mask = int(body.mask.bits)
        if kelvin and (rgb == (0, 0, 0) or model == "H6125"):
            return ParsedStaticWrite(
                operation=operation,
                segment_mask=mask,
                whole_device_mask=whole_device_mask,
                kelvin=kelvin,
                kelvin_companion_rgb=(
                    int(body.rgb_preview.red),
                    int(body.rgb_preview.green),
                    int(body.rgb_preview.blue),
                ),
            )
        return ParsedStaticWrite(
            operation=operation,
            segment_mask=mask,
            whole_device_mask=whole_device_mask,
            rgb=rgb,
        )
    if hasattr(body, "percent"):
        return ParsedStaticWrite(
            operation=operation,
            segment_mask=int(body.mask.bits),
            whole_device_mask=whole_device_mask,
            brightness_pct=int(body.percent),
        )
    return None
