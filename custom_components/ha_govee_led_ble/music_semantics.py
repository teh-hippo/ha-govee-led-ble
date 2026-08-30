"""Exact-profile music parameter semantics, independent of native selectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .const import ModelProfile


@dataclass(frozen=True)
class MusicParamSpec:
    key: str
    profile_key: str
    wire_field: str
    kind: Literal["number", "switch", "select"]
    default: int | bool | str
    min_value: int = 0
    max_value: int = 0
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class MusicVariant:
    mode_code: int
    evidence: str
    layout: str | None = None
    template: bytes = b""
    parameters: tuple[MusicParamSpec, ...] = ()
    supports_style: bool = False
    calm_default: bool = False
    requires_physical_ic_count: bool = False
    # Semantics are qualified independently of the structural tail type.
    gradient_companions: tuple[int, int] | None = None
    style_companions: tuple[int, int] | None = None
    piano_derived_half: bool = False
    direction_values: tuple[tuple[str, int, int], ...] = ()


# Captured values, not values calculated from logical colour zones or guessed IC counts.
H617A_MUSIC_VARIANTS = (
    MusicVariant(0x03, "H617A qualified selector style", supports_style=True),
    MusicVariant(
        0x30,
        "H617A captured Bloom companion",
        "music_body",
        bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000"),
        supports_style=True,
        style_companions=(0x50, 0x14),
    ),
    MusicVariant(
        0x31,
        "H617A captured Shiny companion",
        "music_body",
        bytes.fromhex("3105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
        supports_style=True,
        style_companions=(0x0564, 0x1446),
    ),
    MusicVariant(
        0x32,
        "H617A qualified Separation captures",
        "music_body",
        bytes.fromhex("3205ff7f00ff0000ffff000000ff00ff0001015e0000000000000000000000"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 1, 1, 5),
            MusicParamSpec("music_separation_gradient", "gradient", "gradient", "switch", True),
        ),
        gradient_companions=(0x61, 0x5E),
    ),
    MusicVariant(
        0x33,
        "H617A qualified Hopping captures",
        "music_body",
        bytes.fromhex(
            "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
        ),
        (MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 50, 0, 50),),
    ),
    MusicVariant(
        0x34,
        "H617A qualified Piano Keys captures; captured key-count/half relationship",
        "music_body",
        bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
        (MusicParamSpec("music_piano_key_count", "key_count", "key_count", "number", 15, 8, 15),),
        piano_derived_half=True,
    ),
    MusicVariant(
        0x35,
        "H617A qualified Fountain captures; speed pinned to captured 0x50",
        "music_body",
        bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0001055000000000"),
        (
            MusicParamSpec(
                "music_fountain_direction",
                "direction",
                "piece_num",
                "select",
                "clockwise",
                options=("clockwise", "counterclockwise", "two_way"),
            ),
        ),
        direction_values=(("clockwise", 0, 5), ("counterclockwise", 2, 5), ("two_way", 1, 3)),
    ),
    MusicVariant(
        0x37,
        "H617A qualified Day and Night captures",
        "music_body",
        bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
        (
            MusicParamSpec("music_daynight_segments", "segment_count", "segment_count", "number", 1, 1, 7),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 10, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
    ),
)

H6125_MUSIC_VARIANTS = (
    MusicVariant(0x10, "H6125 captured Energetic selector"),
    MusicVariant(0x11, "H6125 captured Rhythm selector", supports_style=True),
    MusicVariant(0x12, "H6125 captured Spectrum selector"),
    MusicVariant(0x13, "H6125 captured Rolling selector"),
    MusicVariant(
        0x30,
        "H6125 captured Bloom companion",
        "h6125_music_body",
        bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50"),
        supports_style=True,
    ),
    MusicVariant(
        0x31,
        "H6125 captured Shiny companion",
        "h6125_music_body",
        bytes.fromhex("3107ff0000ff7f00ffff0000ff000000ff00ffff8b00ff05640a"),
        supports_style=True,
    ),
    MusicVariant(
        0x32,
        "H6125 captured Separation companion",
        "h6125_music_body",
        bytes.fromhex("3207ff0000ff7f00ffff0000ff000000ff00ffff8b00ff030063"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 3, 1, 5),
            MusicParamSpec("music_separation_gradient", "gradient", "gradient", "switch", False),
        ),
    ),
    MusicVariant(
        0x33,
        "H6125 captured Hopping companion",
        "h6125_music_body",
        bytes.fromhex("3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010101196201030614"),
        (MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 25, 0, 50),),
    ),
    MusicVariant(
        0x34,
        "H6125 captured Piano Keys companion",
        "h6125_music_body",
        bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f230107"),
        (MusicParamSpec("music_piano_key_count", "key_count", "key_count", "number", 15, 8, 15),),
        piano_derived_half=True,
    ),
    MusicVariant(
        0x35,
        "H6125 captured Fountain companion",
        "h6125_music_body",
        bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff01020555"),
        (
            MusicParamSpec(
                "music_fountain_direction",
                "direction",
                "piece_num",
                "select",
                "clockwise",
                options=("clockwise", "counterclockwise"),
            ),
        ),
    ),
    MusicVariant(
        0x37,
        "H6125 captured Day and Night companion",
        "h6125_music_body",
        bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff071400"),
        (
            MusicParamSpec("music_daynight_segments", "segment_count", "segment_count", "number", 7, 1, 7),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 20, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
    ),
)


def music_variant(profile: ModelProfile, mode_code: int) -> MusicVariant | None:
    return next((variant for variant in profile.music_variants if variant.mode_code == mode_code), None)


def music_parameters_available(profile: ModelProfile, variant: MusicVariant) -> bool:
    return not variant.requires_physical_ic_count or profile.physical_ic_count is not None


def music_params_for_mode(mode_code: int, profile: ModelProfile) -> tuple[MusicParamSpec, ...]:
    variant = music_variant(profile, mode_code)
    return (
        variant.parameters
        if variant is not None
        and variant.layout in {"music_body", "h6125_music_body"}
        and music_parameters_available(profile, variant)
        else ()
    )


def compile_music_parameters(
    raw: Mapping[str, Any], mode_code: int, profile: ModelProfile
) -> dict[str, int | bool | str]:
    relevant = music_params_for_mode(mode_code, profile)
    unsupported = sorted(set(raw).difference(spec.profile_key for spec in relevant))
    if unsupported:
        raise ValueError(f"music mode does not support parameter {unsupported[0]} (unqualified or unavailable)")
    compiled: dict[str, int | bool | str] = {}
    for spec in relevant:
        value = raw.get(spec.profile_key, spec.default)
        if spec.kind == "number":
            if type(value) is not int or not spec.min_value <= value <= spec.max_value:
                raise ValueError(f"{spec.profile_key} must be an integer from {spec.min_value} to {spec.max_value}")
        elif spec.kind == "switch":
            if not isinstance(value, bool):
                raise ValueError(f"{spec.profile_key} must be a boolean")
        elif not isinstance(value, str) or value not in spec.options:
            raise ValueError(f"{spec.profile_key} must be one of {', '.join(spec.options)}")
        compiled[spec.profile_key] = value
    return compiled


def capture_music_parameters(
    source: object,
    profile: ModelProfile,
    mode: str,
    model: str,
) -> dict[str, int | bool | str]:
    """New snapshots always carry a mapping; only legacy persisted snapshots omit it."""
    from .const import music_mode_code

    if mode not in profile.music_modes:
        return {}
    return {
        spec.profile_key: getattr(source, spec.key, spec.default)
        for spec in music_params_for_mode(music_mode_code(model, mode), profile)
    }
