"""Semantic encoders for device DIY definitions."""

from collections.abc import Sequence
from dataclasses import dataclass

from .effect_domain import H6179MixedDiyEffect, H6179SingleDiyEffect
from .generated_protocol_adapter import (
    build_h617a_diy_activation as build_diy_activation,
)
from .generated_protocol_adapter import (
    build_h617a_diy_multi_body,
    build_h617a_diy_painted_body,
    build_h617a_diy_single_body,
)
from .h6179_effect_codec import encode_h6179_effect
from .light_commands import SEGMENT_COUNT
from .protocol_core import DIY_PAINTED_EFFECTS
from .protocol_h6179 import build_h6179_diy_activation as build_h6179_activation
from .protocol_h6199 import build_h6199_palette_diy_envelope
from .transport import fragment_a1_02, fragment_a3, fragment_a3_envelope

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
    if not 1 <= len(palette) <= 0xFF // 3:
        raise ValueError("palette must contain 1 to 85 colours")
    for colour in palette:
        _validate_rgb(colour, "palette colour")


def build_h617a_diy_painted(
    effect: str,
    speed: int,
    brightness: int,
    background: RGB,
    groups: Sequence[DiyPaintGroup] = (),
    *,
    segment_count: int = SEGMENT_COUNT,
) -> list[bytes]:
    if not isinstance(segment_count, int) or isinstance(segment_count, bool) or not 1 <= segment_count <= 255:
        raise ValueError("painted address count must be from 1 to 255")
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
            if not isinstance(segment, int) or not 0 <= segment < segment_count:
                raise ValueError(f"painted segment {segment} out of range 0..{segment_count - 1}")
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


def build_h6179_diy(
    content: H6179SingleDiyEffect | H6179MixedDiyEffect,
) -> list[bytes]:
    return fragment_a1_02(encode_h6179_effect(content))


def build_h6179_diy_activation(diy_code: int) -> bytes:
    return build_h6179_activation(diy_code)


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


def _frame_type04(body: bytes, a1_selector: int | None) -> list[bytes]:
    if a1_selector is None:
        return fragment_a3(0x04, body)
    return fragment_a1_02(bytes([a1_selector]) + body)


def build_h617a_diy_single(
    family: int,
    variant: int,
    speed: int,
    palette: Sequence[RGB],
    *,
    a1_selector: int | None = None,
) -> list[bytes]:
    _validate_byte(family, "family")
    if family == 0xFF:
        raise ValueError("family 255 is reserved for Multi")
    _validate_byte(variant, "variant")
    _validate_percent(speed, "speed")
    _validate_palette(palette)
    return _frame_type04(build_h617a_diy_single_body(family, variant, speed, list(palette)), a1_selector)


def build_h617a_diy_multi(
    effects: Sequence[tuple[int, int]],
    speed: int,
    palette: Sequence[RGB],
    *,
    a1_selector: int | None = None,
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
    return _frame_type04(build_h617a_diy_multi_body(encoded_effects, speed, list(palette)), a1_selector)
