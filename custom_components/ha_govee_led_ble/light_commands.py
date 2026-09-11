"""Semantic colour, temperature, segment and brightness commands."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .const import ModelProfile, get_profile
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


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def segments_to_mask(segments: Iterable[int], profile: ModelProfile | None = None) -> int:
    """Validate one-based indices, optionally for a target, and build a 15-bit mask."""
    if profile is not None and not profile.supports_segments:
        raise ValueError(f"{profile.name} does not support per-segment control")
    count = SEGMENT_COUNT if profile is None else min(SEGMENT_COUNT, profile.segment_count)
    mask = 0
    for segment in segments:
        if not isinstance(segment, int) or isinstance(segment, bool):
            raise ValueError("segment indices must be integers")
        if not 1 <= segment <= count:
            raise ValueError(f"segment {segment} out of range 1..{count}")
        mask |= 1 << (segment - 1)
    if not mask:
        raise ValueError("no segments selected")
    return mask


def build_segment_color(
    segments: Iterable[int],
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    return build_segment_colour(segments_to_mask(segments, profile or get_profile(model)), red, green, blue, model)


def build_segment_brightness(
    segments: Iterable[int],
    percent: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    return build_segment_brightness_mask(segments_to_mask(segments, profile or get_profile(model)), percent, model)


def build_segment_paint(
    groups: Iterable[SegmentColorGroup],
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> list[bytes]:
    """Build one packet for each group because distinct colours require distinct writes."""
    packets = [
        build_segment_color(segments, red, green, blue, model, profile=profile)
        for segments, (red, green, blue) in groups
    ]
    if not packets:
        raise ValueError("at least one non-empty segment group is required")
    return packets


def build_color_rgb(red: int, green: int, blue: int, model: str = "H617A") -> bytes:
    return build_segment_colour(get_profile(model).whole_device_mask, red, green, blue, model)


def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
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
    value = _clamp(kelvin, profile.min_color_temp_kelvin, profile.max_color_temp_kelvin)
    return build_colour_temperature(value, kelvin_to_rgb(value), profile.whole_device_mask, model)


def build_white_brightness(percent: int, model: str = "H617A") -> bytes:
    return build_segment_brightness_mask(get_profile(model).whole_device_mask, percent, model)


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
    if get_profile(model).command_grammar == "H6199":
        if generated.opcode.name != "mode" or getattr(generated.body.sub_mode, "name", None) != "static_colour":
            return None
        detail = generated.body.detail
        operation = int(detail.operation)
        if detail.operation.name == "colour":
            rgb = (int(detail.red), int(detail.green), int(detail.blue))
            kelvin = int(detail.kelvin)
            if rgb == (0, 0, 0) and kelvin:
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
        if rgb == (0, 0, 0) and kelvin:
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
