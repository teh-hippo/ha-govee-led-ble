"""Semantic encoders for device DIY definitions."""

from collections.abc import Sequence
from dataclasses import dataclass

from .generated_protocol_adapter import (
    DIY_PAINTED_EFFECTS,
    build_h617a_diy_multi_body,
    build_h617a_diy_painted_body,
    build_h617a_diy_single_body,
    build_h6199_palette_diy_envelope,
    build_h6199_scene,
)
from .generated_protocol_adapter import (
    build_h617a_diy_activation as build_diy_activation,
)
from .light_commands import SEGMENT_COUNT
from .transport import fragment_a3, fragment_a3_envelope

type RGB = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class DiyPaintGroup:
    fill: RGB
    segments: tuple[int, ...]


def _validate_percent(value: int, name: str) -> None:
    if not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError(f"{name} must be an integer from 0 to 100")


def _validate_byte(value: int, name: str) -> None:
    if not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be an integer from 0 to 255")


def _validate_rgb(value: RGB, name: str) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) != 3
        or any(not isinstance(channel, int) or not 0 <= channel <= 0xFF for channel in value)
    ):
        raise ValueError(f"{name} must be an RGB tuple with channels from 0 to 255")


def _validate_palette(palette: Sequence[RGB]) -> None:
    if not 1 <= len(palette) <= 8:
        raise ValueError("palette must contain 1 to 8 colours")
    for colour in palette:
        _validate_rgb(colour, "palette colour")


def build_h617a_diy_painted(
    effect: str,
    speed: int,
    brightness: int,
    background: RGB,
    groups: Sequence[DiyPaintGroup] = (),
) -> list[bytes]:
    if effect not in DIY_PAINTED_EFFECTS:
        raise ValueError(f"unknown painted effect: {effect}")
    _validate_percent(speed, "speed")
    _validate_percent(brightness, "brightness")
    _validate_rgb(background, "background")
    seen_segments: set[int] = set()
    encoded_groups: list[tuple[RGB, list[int]]] = []
    for group in groups:
        _validate_rgb(group.fill, "paint-group fill")
        if not group.segments:
            raise ValueError("paint group must include at least one segment")
        segments = list(group.segments)
        for segment in segments:
            if not isinstance(segment, int) or not 0 <= segment < SEGMENT_COUNT:
                raise ValueError(f"painted segment {segment} out of range 0..{SEGMENT_COUNT - 1}")
            if segment in seen_segments:
                raise ValueError(f"painted segment {segment} appears in more than one group")
            seen_segments.add(segment)
        encoded_groups.append((group.fill, segments))
    body = build_h617a_diy_painted_body(effect, speed, brightness, background, encoded_groups)
    return fragment_a3(0x03, body)


def build_h617a_diy_activation(diy_code: int) -> bytes:
    if not isinstance(diy_code, int) or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    return build_diy_activation(diy_code)


def build_h6199_palette_diy(
    family: int,
    variant: int,
    speed: int,
    palette: Sequence[RGB],
) -> list[bytes]:
    _validate_byte(family, "effect family")
    _validate_byte(variant, "effect variant")
    _validate_percent(speed, "speed")
    _validate_palette(palette)
    envelope = build_h6199_palette_diy_envelope(family, variant, speed, tuple(palette))
    return fragment_a3_envelope(envelope)


def build_h6199_palette_diy_activation(scene_code: int, music_code: int) -> bytes:
    if not isinstance(scene_code, int) or not 0 <= scene_code <= 0xFFFF:
        raise ValueError("scene code must be an integer from 0 to 65535")
    if not isinstance(music_code, int) or not 0 <= music_code <= 0xFFFF:
        raise ValueError("music code must be an integer from 0 to 65535")
    return build_h6199_scene(scene_code, music_code)


def build_h617a_diy_single(
    family: int,
    variant: int,
    speed: int,
    palette: Sequence[RGB],
) -> list[bytes]:
    _validate_byte(family, "family")
    if family == 0xFF:
        raise ValueError("family 255 is reserved for Multi")
    _validate_byte(variant, "variant")
    _validate_percent(speed, "speed")
    _validate_palette(palette)
    return fragment_a3(0x04, build_h617a_diy_single_body(family, variant, speed, list(palette)))


def build_h617a_diy_multi(
    effects: Sequence[tuple[int, int]],
    speed: int,
    palette: Sequence[RGB],
) -> list[bytes]:
    if not 1 <= len(effects) <= 4:
        raise ValueError("Multi must contain 1 to 4 effects")
    encoded_effects: list[tuple[int, int]] = []
    for family, variant in effects:
        _validate_byte(family, "effect family")
        if family == 0xFF:
            raise ValueError("effect family 255 is reserved for Multi")
        _validate_byte(variant, "effect variant")
        encoded_effects.append((family, variant))
    _validate_percent(speed, "speed")
    _validate_palette(palette)
    return fragment_a3(0x04, build_h617a_diy_multi_body(encoded_effects, speed, list(palette)))
