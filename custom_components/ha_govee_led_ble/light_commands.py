"""Semantic colour, temperature, segment and brightness commands."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .const import ModelProfile, get_profile
from .generated_protocol_adapter import build_colour_temperature, build_segment_colour, parse_command, table_kelvin_rgb
from .generated_protocol_adapter import (
    build_segment_brightness as build_segment_brightness_mask,
)
from .protocol_h6179 import parse_h6179_command

SEGMENT_COUNT = 15
ALL_SEGMENTS: tuple[int, ...] = tuple(range(1, SEGMENT_COUNT + 1))
ALL_SEGMENTS_MASK = 0x7FFF

type SegmentColorGroup = tuple[Iterable[int], tuple[int, int, int]]


def scale_segment_groups(groups: Iterable[SegmentColorGroup], rgb_scale: int = 100) -> list[SegmentColorGroup]:
    """Freeze an explicit palette and scale it once, without reading previous output."""
    if type(rgb_scale) is not int or not 0 <= rgb_scale <= 100:
        raise ValueError("RGB scale must be an integer percentage")
    resolved: list[SegmentColorGroup] = []
    for segments, rgb in groups:
        colour = tuple(rgb)
        if len(colour) != 3 or any(type(channel) is not int or not 0 <= channel <= 255 for channel in colour):
            raise ValueError("RGB colour must contain three byte values")
        red, green, blue = ((channel * rgb_scale + 50) // 100 for channel in colour)
        resolved.append((tuple(segments), (red, green, blue)))
    if not resolved:
        raise ValueError("At least one segment group is required")
    return resolved


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def segments_to_mask(segments: Iterable[int], profile: ModelProfile | None = None) -> int:
    """Validate one-based indices against the target's selectable geometry."""
    if profile is not None and not profile.supports_segments:
        raise ValueError(f"{profile.name} does not support per-segment control")
    count = SEGMENT_COUNT if profile is None else profile.segment_count
    mask = 0
    for segment in segments:
        if not isinstance(segment, int) or isinstance(segment, bool):
            raise ValueError("segment indices must be integers")
        if not 1 <= segment <= count:
            raise ValueError(f"segment {segment} out of range 1..{count}")
        mask |= 1 << (segment - 1)
    if not mask:
        raise ValueError("no segments selected")
    if profile is not None and mask & ~profile.whole_device_mask:
        raise ValueError("segment mask outside profile geometry")
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
    profile = profile or get_profile(model)
    mask = segments_to_mask(segments, profile)
    if not profile.supports_rgb:
        raise ValueError(f"{profile.name} does not support RGB colour")
    return build_segment_colour(mask, red, green, blue, model, profile=profile)


def build_segment_brightness(
    segments: Iterable[int],
    percent: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    mask = segments_to_mask(segments, profile)
    if not profile.supports_segment_brightness:
        raise ValueError(f"{profile.name} does not support segment brightness")
    return build_segment_brightness_mask(mask, percent, model, profile=profile)


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


def build_color_rgb(
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_rgb:
        raise ValueError(f"{profile.name} does not support RGB colour")
    return build_segment_colour(profile.whole_device_mask, red, green, blue, model, profile=profile)


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


def kelvin_companion_rgb(kelvin: int, profile: ModelProfile) -> tuple[int, int, int]:
    return (
        table_kelvin_rgb(kelvin)
        if profile.command_grammar == "H601C" or profile.kelvin_direct_rgb == (255, 255, 255)
        else kelvin_to_rgb(kelvin)
    )


def build_color_temp(kelvin: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    if not profile.supports_color_temperature:
        raise ValueError(f"{profile.name} does not support colour temperature")
    value = _clamp(kelvin, profile.min_color_temp_kelvin, profile.max_color_temp_kelvin)
    return build_colour_temperature(
        value, kelvin_companion_rgb(value, profile), profile.whole_device_mask, model, profile=profile
    )


def build_segment_color_temp(
    segments: Iterable[int],
    kelvin: int,
    model: str = "H617A",
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    """Build masked Kelvin with its rendered RGB companion, using the target bounds."""
    profile = profile or get_profile(model)
    mask = segments_to_mask(segments, profile)
    if not profile.supports_color_temperature:
        raise ValueError(f"{profile.name} does not support colour temperature")
    if not profile.supports_segment_color_temperature:
        raise ValueError(f"{profile.name} does not support segment colour temperature")
    if isinstance(kelvin, bool) or not isinstance(kelvin, int):
        raise ValueError("Kelvin must be an integer")
    if not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin:
        raise ValueError("Kelvin outside profile range")
    return build_colour_temperature(kelvin, kelvin_companion_rgb(kelvin, profile), mask, model, profile=profile)


def build_white_brightness(percent: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    profile = profile or get_profile(model)
    return build_segment_brightness_mask(profile.whole_device_mask, percent, model, profile=profile)


@dataclass(frozen=True)
class ParsedStaticWrite:
    """Static-command fields used by optimistic state and the BLE simulator."""

    operation: int
    segment_mask: int | None
    whole_device_mask: int = ALL_SEGMENTS_MASK
    rgb: tuple[int, int, int] | None = None
    kelvin: int | None = None
    kelvin_companion_rgb: tuple[int, int, int] | None = None
    brightness_pct: int | None = None

    @property
    def whole_strip(self) -> bool:
        return self.segment_mask is None or self.segment_mask == self.whole_device_mask


def parse_static_write(
    packet: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ParsedStaticWrite | None:
    """Convert a generated static command into optimistic semantic state."""
    profile = profile or get_profile(model)
    if profile.command_grammar == "H6179":
        command = parse_h6179_command(packet)
        if command is None or command.operation != "mode" or command.values.get("mode") != "static":
            return None
        kelvin = int(command.values["kelvin"])
        if kelvin:
            return ParsedStaticWrite(
                operation=int(command.values["raw_mode"]),
                segment_mask=None,
                whole_device_mask=0,
                kelvin=kelvin,
                kelvin_companion_rgb=command.values["preview_rgb"],
            )
        return ParsedStaticWrite(
            operation=int(command.values["raw_mode"]),
            segment_mask=None,
            whole_device_mask=0,
            rgb=command.values["rgb"],
        )
    generated = parse_command(packet, model, profile=profile)
    if generated is None or not hasattr(generated.opcode, "name"):
        return None
    whole_device_mask = profile.whole_device_mask
    if profile.command_grammar == "H601C":
        if not generated.is_static:
            return None
        detail = generated.body.detail
        rgb = (int(detail.rgb.red), int(detail.rgb.green), int(detail.rgb.blue))
        kelvin = int(detail.kelvin)
        if kelvin and rgb != (255, 255, 255):
            raise ValueError("H601C Kelvin requires direct white RGB")
        if kelvin and (kelvin - 2700) % 100:
            raise ValueError("H601C Kelvin must use 100 K steps from 2700 to 6500")
        return ParsedStaticWrite(
            operation=int(generated.body.sub_mode),
            segment_mask=whole_device_mask,
            whole_device_mask=whole_device_mask,
            rgb=None if kelvin else rgb,
            kelvin=kelvin or None,
            kelvin_companion_rgb=(
                int(detail.companion_rgb.red),
                int(detail.companion_rgb.green),
                int(detail.companion_rgb.blue),
            )
            if kelvin
            else None,
        )
    if profile.command_grammar in {"H6099", "H6199"}:
        if generated.opcode.name != "mode" or getattr(generated.body.sub_mode, "name", None) != "static_colour":
            return None
        detail = generated.body.detail
        operation = int(detail.operation)
        if detail.operation.name == "colour":
            rgb = (int(detail.red), int(detail.green), int(detail.blue))
            kelvin = int(detail.kelvin)
            if kelvin and profile.kelvin_direct_rgb == (255, 255, 255) and rgb != profile.kelvin_direct_rgb:
                raise ValueError("Kelvin direct RGB does not match the profile")
            if rgb == profile.kelvin_direct_rgb and kelvin:
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
        sentinel = profile.kelvin_direct_rgb
        if kelvin and sentinel == (255, 255, 255) and rgb != sentinel:
            raise ValueError("Kelvin requires direct white RGB")
        if rgb == sentinel and kelvin:
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
