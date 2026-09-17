"""Exact-profile music parameter semantics, independent of native selectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import ceil
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
    requires_physical_ic_count: bool = False


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
    palette_bounds: tuple[int, int] | None = None
    supports_fixed_colour: bool = True
    physical_defaults: str | None = None


# Captured values, not values calculated from logical colour zones or guessed IC counts.
H617A_MUSIC_VARIANTS = (
    MusicVariant(0x03, "H617A qualified selector style", supports_style=True),
    MusicVariant(0x04, "H617A APK MusicFragmentV3 / DialogOldMusicV0; fixed-colour register readback"),
    MusicVariant(0x05, "H617A APK AbsNewMusicFragment.E0: Energetic has no editor", supports_fixed_colour=False),
    MusicVariant(0x06, "H617A APK MusicFragmentV3 / DialogOldMusicV0; fixed-colour register readback"),
    MusicVariant(
        0x30,
        "H617A captured Bloom companion",
        "music_body",
        bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000"),
        supports_style=True,
        style_companions=(0x50, 0x14),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x31,
        "H617A captured Shiny companion",
        "music_body",
        bytes.fromhex("3105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
        supports_style=True,
        style_companions=(0x0564, 0x1446),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x32,
        "H617A qualified Separation captures",
        "music_body",
        bytes.fromhex("3205ff7f00ff0000ffff000000ff00ff0001015e0000000000000000000000"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 1, 1, 5),
            MusicParamSpec(
                "music_separation_gradient", "gradient", "gradient", "switch", True, requires_physical_ic_count=True
            ),
        ),
        gradient_companions=(0x61, 0x5E),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x33,
        "H617A qualified Hopping captures",
        "music_body",
        bytes.fromhex(
            "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
        ),
        (
            MusicParamSpec("music_hopping_background", "background", "background", "number", 0xFF0000, 0, 0xFFFFFF),
            MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 50, 0, 50),
        ),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x34,
        "H617A captured Piano preset; APK GangQinJian gradient and physical-IC key bounds",
        "music_body",
        bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
        (
            MusicParamSpec(
                "music_piano_key_count", "key_count", "key_count", "number", 15, 8, 15, requires_physical_ic_count=True
            ),
            MusicParamSpec("music_piano_gradient", "gradient", "gradient", "switch", False),
        ),
        piano_derived_half=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
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
                requires_physical_ic_count=True,
            ),
        ),
        direction_values=(("clockwise", 0, 5), ("counterclockwise", 2, 5), ("two_way", 1, 3)),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x37,
        "H617A qualified Day and Night captures",
        "music_body",
        bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
        (
            MusicParamSpec(
                "music_daynight_segments",
                "segment_count",
                "piece_count",
                "number",
                1,
                1,
                7,
                requires_physical_ic_count=True,
            ),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 10, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
)


# H617E's pre-R5/R6 qualified presets, independently declared. Shared wire layout
# does not inherit H617A's new authoring permissions or physical-IC policy.
H617E_MUSIC_VARIANTS = (
    MusicVariant(0x03, "H617E owner-qualified shared music semantics", supports_style=True),
    MusicVariant(
        0x30,
        "H617E owner-qualified shared music semantics",
        "music_body",
        bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000"),
        supports_style=True,
        style_companions=(0x50, 0x14),
    ),
    MusicVariant(
        0x31,
        "H617E owner-qualified shared music semantics",
        "music_body",
        bytes.fromhex("3105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
        supports_style=True,
        style_companions=(0x0564, 0x1446),
    ),
    MusicVariant(
        0x32,
        "H617E owner-qualified shared music semantics",
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
        "H617E owner-qualified shared music semantics",
        "music_body",
        bytes.fromhex(
            "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
        ),
        (MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 50, 0, 50),),
    ),
    MusicVariant(
        0x34,
        "H617E owner-qualified shared music semantics",
        "music_body",
        bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
        (MusicParamSpec("music_piano_key_count", "key_count", "key_count", "number", 15, 8, 15),),
        piano_derived_half=True,
    ),
    MusicVariant(
        0x35,
        "H617E owner-qualified shared music semantics",
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
        "H617E owner-qualified shared music semantics",
        "music_body",
        bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
        (
            MusicParamSpec("music_daynight_segments", "segment_count", "piece_count", "number", 1, 1, 7),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 10, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
    ),
)


# Android 7.6.01 pact_h6099/detail/mode/MusicMode and MusicEffect.Companion.a.
# These are unpadded APK bodies, not H617A capture templates.
_H6099_PALETTE = "07ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"
H6099_MUSIC_VARIANTS = (
    MusicVariant(3, "H6099 MusicMode.d Rhythm legacy selector", supports_style=True),
    MusicVariant(4, "H6099 MusicMode.d Spectrum legacy selector"),
    MusicVariant(5, "H6099 SubModeMusicV1 legacy Energetic selector; new-detail upload path unresolved"),
    MusicVariant(6, "H6099 MusicMode.d Rolling legacy selector"),
    MusicVariant(
        0x30,
        "H6099 MusicMode.d / RgbMusicZhanFang",
        "h6099_music_parameters",
        bytes.fromhex("30" + _H6099_PALETTE + "0a50"),
        supports_style=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x31,
        "H6099 MusicMode.d / RgbMusicCuiCan",
        "h6099_music_parameters",
        bytes.fromhex("31" + _H6099_PALETTE + "05640a"),
        supports_style=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x32,
        "H6099 MusicMode.d / FenLi.Builder",
        "h6099_music_parameters",
        bytes.fromhex("32" + _H6099_PALETTE + "030061"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 3, 1, 5),
            MusicParamSpec("music_separation_gradient", "gradient", "gradient", "switch", False),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x33,
        "H6099 MusicMode.d / RgbicMusicYueDong; ColorUtils.toNoColor = RGB 1,1,1",
        "h6099_music_parameters",
        bytes.fromhex("33" + _H6099_PALETTE + "010101196201030000"),
        (
            MusicParamSpec("music_hopping_background", "background", "background", "number", 0x010101, 0, 0xFFFFFF),
            MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 25, 0, 50),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x34,
        "H6099 MusicMode.d / RgbicMusicGangQinJian",
        "h6099_music_parameters",
        bytes.fromhex("34" + _H6099_PALETTE + "0000000000"),
        (
            MusicParamSpec("music_piano_key_count", "key_count", "key_count", "number", 0),
            MusicParamSpec("music_piano_gradient", "gradient", "gradient", "switch", False),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x35,
        "H6099 MusicMode.d / RgbicMusicDuiJi",
        "h6099_music_parameters",
        bytes.fromhex("35" + _H6099_PALETTE + "01000000"),
        (
            MusicParamSpec(
                "music_fountain_direction",
                "direction",
                "start_point",
                "select",
                "two_way",
                options=("clockwise", "counterclockwise", "two_way"),
            ),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x37,
        "H6099 MusicMode.d case 55: default piece retained, UI indices 0/1 used as speed/fade",
        "h6099_music_parameters",
        bytes.fromhex("37" + _H6099_PALETTE + "000000"),
        # The APK never calls setPiece and ignores UI index 2. Do not advertise those controls.
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
)

# RGBIC AcNewDetail MusicMode.d shares these named palette/tail encodings;
# its Day/Night indices and Piano defaults differ from H6099 and are explicit.
H6102_MUSIC_VARIANTS = (
    MusicVariant(5, "RGBIC MusicMode.d basic Energetic", supports_fixed_colour=False),
    MusicVariant(3, "RGBIC MusicMode.d basic Rhythm", supports_style=True),
    MusicVariant(4, "RGBIC MusicMode.d basic Spectrum"),
    MusicVariant(6, "RGBIC MusicMode.d basic Rolling"),
    *(
        replace(
            variant,
            evidence="H6102 RGBIC MusicMode.d, palette/tail shared with H6099",
            physical_defaults="rgbic",
            parameters=tuple(
                replace(
                    spec,
                    requires_physical_ic_count=(variant.mode_code, spec.profile_key)
                    in {(0x32, "gradient"), (0x34, "key_count"), (0x35, "direction")},
                )
                for spec in variant.parameters
            ),
        )
        for variant in H6099_MUSIC_VARIANTS
        if variant.mode_code in (0x30, 0x31, 0x32, 0x33, 0x34, 0x35)
    ),
    MusicVariant(
        0x37,
        "H6102 RGBIC MusicMode.d case 55; Support.t/u/v",
        "music_body",
        bytes.fromhex("37" + _H6099_PALETTE + "071400"),
        (
            MusicParamSpec(
                "music_daynight_segments",
                "segment_count",
                "piece_count",
                "number",
                7,
                1,
                7,
                requires_physical_ic_count=True,
            ),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 20, 1, 100),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
        physical_defaults="rgbic",
    ),
)


def music_variant(profile: ModelProfile, mode_code: int) -> MusicVariant | None:
    variant = next((variant for variant in profile.music_variants if variant.mode_code == mode_code), None)
    ic = profile.physical_ic_count
    if (
        variant
        and mode_code == 0x34
        and ic is not None
        and (
            variant.layout == "h6099_music_parameters"
            or any(spec.requires_physical_ic_count for spec in variant.parameters)
        )
    ):
        minimum, maximum = (ceil(ic / 2), ic) if ic < 30 else (9, max(9, ceil(ic * 3 / 5)))
        default = ceil(ic * 3 / 4) if ic < 30 else ceil(ic * 3 / 10)
        if variant.physical_defaults == "rgbic":
            default = ic * 3 // 4 if ic < 30 else 15
        if variant.physical_defaults != "rgbic" and (
            variant.layout == "music_body" or int(variant.parameters[0].default) > 0
        ):
            default = max(minimum, min(maximum, int(variant.parameters[0].default)))
        variant = replace(
            variant,
            parameters=(
                replace(variant.parameters[0], default=default, min_value=minimum, max_value=maximum),
                *variant.parameters[1:],
            ),
        )
    if (
        variant
        and variant.layout == "music_body"
        and ic is not None
        and any(spec.requires_physical_ic_count for spec in variant.parameters)
    ):
        if mode_code == 0x32:
            variant = replace(variant, gradient_companions=(99, 98) if ic >= 30 else (97, 94))
        elif mode_code == 0x35:
            pieces = ic // 3 if ic < 30 else ceil(ic * 4 / 25)
            two_way = ic // 4 if ic < 30 else ceil(ic / 10)
            variant = replace(
                variant,
                direction_values=(("clockwise", 0, pieces), ("counterclockwise", 2, pieces), ("two_way", 1, two_way)),
            )
        elif mode_code == 0x37:
            variant = replace(
                variant,
                parameters=(
                    replace(
                        variant.parameters[0],
                        max_value=ic // 2 if ic < 30 else ceil(ic / 5),
                        default=(ic // 2 if ic < 30 else 7)
                        if variant.physical_defaults == "rgbic"
                        else variant.parameters[0].default,
                    ),
                    *variant.parameters[1:],
                ),
            )
    return variant


def music_parameters_available(profile: ModelProfile, variant: MusicVariant) -> bool:
    return not variant.requires_physical_ic_count or profile.physical_ic_count is not None


def retained_music_profile(profile: ModelProfile, mode_code: int) -> ModelProfile:
    """Retained RGBIC geometry permits editing only independently qualified fields."""
    return replace(
        profile,
        music_variants=tuple(
            replace(variant, requires_physical_ic_count=False)
            if variant.mode_code == mode_code and variant.physical_defaults == "rgbic"
            else variant
            for variant in profile.music_variants
        ),
    )


def music_parameters_depend_on_ic(variant: MusicVariant | None, parameters: Mapping[str, Any]) -> bool:
    """Check the actual request, including compiled defaults, not every possible control."""
    return bool(
        variant
        and (
            variant.requires_physical_ic_count
            or any(spec.requires_physical_ic_count and spec.profile_key in parameters for spec in variant.parameters)
        )
    )


def music_params_for_mode(mode_code: int, profile: ModelProfile) -> tuple[MusicParamSpec, ...]:
    variant = music_variant(profile, mode_code)
    return (
        tuple(
            spec
            for spec in variant.parameters
            if not spec.requires_physical_ic_count or profile.physical_ic_count is not None
        )
        if variant is not None
        and variant.layout in {"music_body", "h6099_music_parameters"}
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


def capture_music_parameters(source: object, profile: ModelProfile, mode: str) -> dict[str, int | bool | str]:
    """New snapshots always carry a mapping; only legacy persisted snapshots omit it."""
    from .const import MUSIC_MODE_SLUGS

    if mode not in profile.music_modes:
        return {}
    return {
        spec.profile_key: getattr(source, spec.key, spec.default)
        for spec in music_params_for_mode(MUSIC_MODE_SLUGS[mode], profile)
    }
