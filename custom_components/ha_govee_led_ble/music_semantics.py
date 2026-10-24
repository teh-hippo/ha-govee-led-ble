"""Exact-profile music parameter semantics, independent of native selectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib import import_module
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
    selector_parameters: tuple[MusicParamSpec, ...] = ()
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


# Layouts whose A3 companion carries the effect's parameters; their selectors omit style and fixed colour.
COMPANION_MUSIC_LAYOUTS = frozenset(
    {
        "music_body",
        "h6076_music_body",
        "h6099_music_parameters",
        "h6097_music_parameters",
        "h66a0_music_parameters",
        "h1a42_music_parameters",
        "h61f5_music_parameters",
        "h7025_music_body",
    }
)

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

_H6097_PALETTE = "07ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"
H6097_MUSIC_VARIANTS = (
    MusicVariant(3, "H6097 candidate classic Rhythm selector", supports_style=True),
    MusicVariant(4, "H6097 candidate classic Spectrum selector"),
    MusicVariant(
        5,
        "H6097 candidate Energetic companion; parameter meaning unqualified",
        "h6097_music_parameters",
        bytes.fromhex("05" + _H6097_PALETTE + "0100"),
        supports_fixed_colour=False,
    ),
    MusicVariant(6, "H6097 candidate classic Rolling selector"),
    MusicVariant(
        0x30,
        "H6097 candidate Bloom companion",
        "h6097_music_parameters",
        bytes.fromhex("30" + _H6097_PALETTE + "0a50"),
        supports_style=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x31,
        "H6097 candidate Shiny companion",
        "h6097_music_parameters",
        bytes.fromhex("31" + _H6097_PALETTE + "05640a"),
        supports_style=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x32,
        "H6097 candidate Separation companion",
        "h6097_music_parameters",
        bytes.fromhex("32" + _H6097_PALETTE + "030061"),
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
        "H6097 candidate Hopping companion",
        "h6097_music_parameters",
        bytes.fromhex("33" + _H6097_PALETTE + "010101196201030000"),
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
        "H6097 candidate Piano Keys companion",
        "h6097_music_parameters",
        bytes.fromhex("34" + _H6097_PALETTE + "0000000000"),
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
        "H6097 candidate Fountain companion",
        "h6097_music_parameters",
        bytes.fromhex("35" + _H6097_PALETTE + "01000000"),
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
        "H6097 candidate Day and Night companion; conflicting editor indices are not exposed",
        "h6097_music_parameters",
        bytes.fromhex("37" + _H6097_PALETTE + "000000"),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
)

# Android 7.6.01 pact_h6099/detail/mode/MusicModeH66A0, goods 327.
H66A0_MUSIC_VARIANTS = (
    *(
        replace(
            variant,
            evidence=variant.evidence.replace("H6099 MusicMode", "H66A0 MusicModeH66A0"),
            layout="h66a0_music_parameters" if variant.layout == "h6099_music_parameters" else variant.layout,
        )
        for variant in H6099_MUSIC_VARIANTS
        if variant.mode_code in (3, 4, 5, 6, 0x30, 0x32, 0x33, 0x34, 0x35)
    ),
    MusicVariant(
        0x37,
        "H66A0 MusicModeH66A0.d case 55 / RgbicMusicZhouYe",
        "h66a0_music_parameters",
        bytes.fromhex("37" + _H6099_PALETTE + "0d1400"),
        (
            MusicParamSpec(
                "music_daynight_segments",
                "segment_count",
                "piece_count",
                "number",
                13,
                1,
                18,
                requires_physical_ic_count=True,
            ),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 20, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x84,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.makeShuiHua",
        "h66a0_music_parameters",
        bytes.fromhex("84" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x85,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.O0",
        "h66a0_music_parameters",
        bytes.fromhex("85" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x55,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.makeCaihui",
        "h66a0_music_parameters",
        bytes.fromhex("55" + _H6099_PALETTE + "01"),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0xA9,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.makeJiePai",
        "h66a0_music_parameters",
        bytes.fromhex("a9" + _H6099_PALETTE + "0100"),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x78,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.makeWindmill",
        "h66a0_music_parameters",
        bytes.fromhex("78" + _H6099_PALETTE),
        palette_bounds=(2, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x53,
        "H66A0 MusicModeH66A0.d / SubMusicModeConfig.makeFlowingLight",
        "h66a0_music_parameters",
        bytes.fromhex("53" + _H6099_PALETTE + "01"),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
)

# Android 7.6.01 h61d3/adjustNew/music/MusicModeNewH1A43, goods 400 + issue #391 hardware sweep.
H1A42_MUSIC_VARIANTS = (
    *(
        replace(
            variant,
            evidence=variant.evidence.replace("H6099 MusicMode", "H1A42 MusicModeNewH1A43"),
        )
        for variant in H6099_MUSIC_VARIANTS
        if variant.mode_code in (3, 4, 5, 6)
    ),
    MusicVariant(
        0x84,
        "H1A42 MusicModeNewH1A43.d / SubMusicModeConfig.makeShuiHua",
        "h1a42_music_parameters",
        bytes.fromhex("84" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x85,
        "H1A42 MusicModeNewH1A43.d / SubMusicModeConfig.makeTanHuang",
        "h1a42_music_parameters",
        bytes.fromhex("85" + _H6099_PALETTE),
        palette_bounds=(2, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x92,
        "H1A42 MusicModeNewH1A43.d / SubMusicModeConfig.makeFeiDieUFO",
        "h1a42_music_parameters",
        bytes.fromhex("92" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0xA3,
        "H1A42 MusicModeNewH1A43.d / SubMusicModeConfig.makeYouDong",
        "h1a42_music_parameters",
        bytes.fromhex("a3" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
)

# Android 7.6.01 h61d3/adjustNew/music/MusicModeNewH61F6, goods 261 + issue #392 hardware sweep.
H61F5_MUSIC_VARIANTS = (
    *(
        replace(
            variant,
            evidence=(
                "H61F5 MusicModeNewH61F6.d Energetic legacy selector"
                if variant.mode_code == 5
                else variant.evidence.replace("H6099 MusicMode", "H61F5 MusicModeNewH61F6")
            ),
            layout="h61f5_music_parameters" if variant.layout == "h6099_music_parameters" else variant.layout,
        )
        for variant in H6099_MUSIC_VARIANTS
        if variant.mode_code in (3, 4, 5, 6, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35)
    ),
    MusicVariant(
        0x37,
        "H61F5 MusicModeNewH61F6.d case 55 / RgbicMusicZhouYe",
        "h61f5_music_parameters",
        bytes.fromhex("37" + _H6099_PALETTE + "071400"),
        (
            MusicParamSpec(
                "music_daynight_segments",
                "segment_count",
                "piece_count",
                "number",
                7,
                1,
                10,
                requires_physical_ic_count=True,
            ),
            MusicParamSpec("music_daynight_speed", "speed", "speed", "number", 20, 1, 50),
            MusicParamSpec("music_daynight_gradient", "gradient", "gradient", "switch", False),
        ),
        requires_physical_ic_count=True,
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x84,
        "H61F5 MusicModeNewH61F6.d / SubMusicModeConfig.makeShuiHua",
        "h61f5_music_parameters",
        bytes.fromhex("84" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x85,
        "H61F5 MusicModeNewH61F6.d / SubMusicModeConfig.makeTanHuang",
        "h61f5_music_parameters",
        bytes.fromhex("85" + _H6099_PALETTE),
        palette_bounds=(2, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x8B,
        "H61F5 MusicModeNewH61F6.d / SubMusicModeConfig.makeLiuYing",
        "h61f5_music_parameters",
        bytes.fromhex("8b" + _H6099_PALETTE),
        palette_bounds=(4, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x92,
        "H61F5 MusicModeNewH61F6.d / SubMusicModeConfig.makeFeiDieUFO",
        "h61f5_music_parameters",
        bytes.fromhex("92" + _H6099_PALETTE),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0xA3,
        "H61F5 MusicModeNewH61F6.d / SubMusicModeConfig.makeYouDong",
        "h61f5_music_parameters",
        bytes.fromhex("a3" + _H6099_PALETTE),
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

# H6125 pact 1 reaches the same RGBIC MusicMode.d producers as H6102 through the
# dreamcolorlightv1 route; only the selector submode differs, and the transform owns that.
H6125_MUSIC_VARIANTS = H6102_MUSIC_VARIANTS

# H617C uses the same RGBIC MusicMode.d producers through music_body so legacy
# zero-padded H617C recovery bodies and newly authored bodies both validate.
H617C_MUSIC_VARIANTS = tuple(
    replace(
        variant,
        evidence="H617C RGBIC MusicMode.d over music_body",
        layout="music_body" if variant.layout == "h6099_music_parameters" else variant.layout,
        style_companions=(0x50, 0x14)
        if variant.mode_code == 0x30
        else (0x0564, 0x1446)
        if variant.mode_code == 0x31
        else variant.style_companions,
        gradient_companions=(99, 98) if variant.mode_code == 0x32 else variant.gradient_companions,
        piano_derived_half=True if variant.mode_code == 0x34 else variant.piano_derived_half,
        direction_values=(("clockwise", 0, 5), ("counterclockwise", 2, 5), ("two_way", 1, 3))
        if variant.mode_code == 0x35
        else variant.direction_values,
        parameters=tuple(
            replace(spec, wire_field="piece_num")
            if variant.mode_code == 0x35 and spec.profile_key == "direction"
            else spec
            for spec in variant.parameters
        ),
    )
    for variant in H6102_MUSIC_VARIANTS
)

_H6076_MODE = import_module(
    "custom_components.ha_govee_led_ble.generated_protocol.h6076_music_write"
).H6076MusicWrite.MusicMode
# The app's default seven-colour palette; the capture-backed Torch body carries it unchanged.
_H6076_PALETTE = "ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"


def _h6076_body(mode: int, tail: str = "") -> bytes:
    return bytes((mode, 7)) + bytes.fromhex(_H6076_PALETTE + tail)


# Pre-1.02.00 firmware (OldMusicMode) supports the 6 selector-only modes; Energetic is auto-colour only.
H6076_LEGACY_MUSIC_VARIANTS = (
    MusicVariant(
        int(_H6076_MODE.energetic), "H6076 OldMusicMode Energetic: auto-colour only", supports_fixed_colour=False
    ),
    *(
        MusicVariant(int(mode), f"H6076 {mode.name}: fixed-colour flag and RGB in the selector; {evidence}")
        for mode, evidence in (
            (_H6076_MODE.bounce, "capture and app producer"),
            (_H6076_MODE.hopping, "capture and app producer"),
            (_H6076_MODE.beat, "capture and app producer"),
            (_H6076_MODE.spray, "capture and app producer"),
        )
    ),
    MusicVariant(int(_H6076_MODE.rhythm), "H6076 capture and app producer: Dynamic/Calm byte", supports_style=True),
)

# Legacy selectors keep their parameters in the selector; companion-backed effects upload an A3 body first.
H6076_MUSIC_VARIANTS = (
    *(
        MusicVariant(int(mode), f"H6076 {mode.name}: fixed-colour flag and RGB in the selector; {evidence}")
        for mode, evidence in (
            (_H6076_MODE.energetic, "captured"),
            (_H6076_MODE.bounce, "capture and app producer"),
            (_H6076_MODE.hopping, "capture and app producer"),
            (_H6076_MODE.beat, "capture and app producer"),
            (_H6076_MODE.spray, "capture and app producer"),
        )
    ),
    MusicVariant(int(_H6076_MODE.rhythm), "H6076 capture and app producer: Dynamic/Calm byte", supports_style=True),
    MusicVariant(
        int(_H6076_MODE.separation),
        "H6076 capture: default Separation companion, point 2 and gradient off",
        "h6076_music_body",
        _h6076_body(int(_H6076_MODE.separation), "020061"),
        (
            MusicParamSpec("music_separation_point", "point", "point", "number", 2, 1, 3),
            MusicParamSpec(
                "music_separation_gradient",
                "gradient",
                "gradient",
                "switch",
                False,
                requires_physical_ic_count=True,
            ),
        ),
        palette_bounds=(2, 8),
        gradient_companions=(0x61, 0x5E),
        supports_fixed_colour=False,
    ),
    *(
        MusicVariant(
            int(mode),
            f"H6076 {mode.name} default companion; {evidence}",
            "h6076_music_body",
            _h6076_body(int(mode)),
            palette_bounds=bounds,
            supports_fixed_colour=False,
        )
        for mode, bounds, evidence in (
            (_H6076_MODE.torch, (1, 8), "captured"),
            (_H6076_MODE.skittles, (2, 8), "app producer and reporter LAN replay"),
            (_H6076_MODE.candy_crush, (3, 8), "app producer and reporter LAN replay"),
            (_H6076_MODE.fusion, (2, 8), "app producer and reporter LAN replay"),
            (_H6076_MODE.shiny, (4, 8), "app producer and reporter LAN replay"),
        )
    ),
)

H7020_MUSIC_VARIANTS = (
    MusicVariant(
        0x03,
        "H7020 qualified Rhythm selector response",
        selector_parameters=(
            MusicParamSpec(
                "music_rhythm_response",
                "response",
                "rhythm_response",
                "select",
                "soft",
                options=("dynamic", "soft"),
            ),
        ),
    ),
    MusicVariant(0x04, "H7020 qualified Spectrum selector"),
    MusicVariant(0x05, "H7020 qualified Energetic selector"),
    MusicVariant(0x06, "H7020 qualified Rolling selector"),
)


_H7025_PALETTE = "ff0000ff7f00ffff0000ff000000ff00ffff8b00ff"

H7025_MUSIC_VARIANTS = (
    MusicVariant(0x03, "H7025 explicit Rhythm selector, calm flag and one optional fixed RGB", supports_style=True),
    *(
        MusicVariant(
            mode,
            "H7025 colour-only music producer; three trailing body bytes",
            "h7025_music_body",
            bytes.fromhex(f"{mode:02x}07{_H7025_PALETTE}000000"),
            palette_bounds=(1, 8),
            supports_fixed_colour=False,
        )
        for mode in (0x8E, 0x8F)
    ),
    MusicVariant(
        0x59,
        "H7025 Flow: direction, 1..3 groups and five ICs per group",
        "h7025_music_body",
        bytes.fromhex(f"5907{_H7025_PALETTE}000205"),
        (
            MusicParamSpec(
                "music_flow_direction",
                "direction",
                "direction",
                "select",
                "clockwise",
                options=("clockwise", "counterclockwise"),
            ),
            MusicParamSpec("music_flow_groups", "group_count", "group_count", "number", 2, 1, 3),
        ),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x98,
        "H7025 Star: background RGB; final distance byte preserved without a brightness interpretation",
        "h7025_music_body",
        bytes.fromhex(f"9807{_H7025_PALETTE}0000ff03"),
        (MusicParamSpec("music_star_background", "background", "background", "number", 0x0000FF, 0, 0xFFFFFF),),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x48,
        "H7025 Hopping producer and issue #148 background/brightness replay",
        "h7025_music_body",
        bytes.fromhex(f"4807{_H7025_PALETTE}010101030000"),
        (
            MusicParamSpec("music_hopping_background", "background", "background", "number", 0x010101, 0, 0xFFFFFF),
            MusicParamSpec("music_hopping_brightness", "relative_brightness", "rel_brightness", "number", 3, 1, 50),
        ),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x5A,
        "H7025 Rolling direction choices; not a speed parameter",
        "h7025_music_body",
        bytes.fromhex(f"5a07{_H7025_PALETTE}080000"),
        (
            MusicParamSpec(
                "music_rolling_direction",
                "direction",
                "direction",
                "select",
                "spread",
                options=("left", "right", "spread"),
            ),
        ),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x37,
        "H7025 Day and Night: 1..3 pieces; reported default 03 0a 00",
        "h7025_music_body",
        bytes.fromhex(f"3707{_H7025_PALETTE}030a00"),
        (MusicParamSpec("music_daynight_segments", "segment_count", "piece_count", "number", 3, 1, 3),),
        palette_bounds=(1, 8),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x34,
        "H7025 issue #148 Piano tail 00 05 0a 04 04; app limits palette to five and keeps gradient off",
        "h7025_music_body",
        bytes.fromhex("3405ff0000ff7f00ffff0000ff000000ff00050a0404"),
        palette_bounds=(1, 5),
        supports_fixed_colour=False,
    ),
    MusicVariant(
        0x5D,
        "H7025 Separation direction choices and two trailing body bytes",
        "h7025_music_body",
        bytes.fromhex(f"5d07{_H7025_PALETTE}080000"),
        (
            MusicParamSpec(
                "music_separation_direction",
                "direction",
                "direction",
                "select",
                "spread",
                options=("left", "right", "spread", "gather"),
            ),
        ),
        palette_bounds=(2, 8),
        supports_fixed_colour=False,
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
            variant.layout
            in {"h6097_music_parameters", "h6099_music_parameters", "h66a0_music_parameters", "h61f5_music_parameters"}
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
        and mode_code == 0x37
        and variant.layout
        in {"h6097_music_parameters", "h6099_music_parameters", "h66a0_music_parameters", "h61f5_music_parameters"}
        and variant.parameters
        and ic is not None
    ):
        max_value = max(1, ic // 2) if ic < 30 else ceil(ic / 5)
        default = max(1, ic // 2) if ic < 30 else ceil(ic * 7 / 50)
        speed_default = 10 if ic < 30 else 20
        variant = replace(
            variant,
            parameters=(
                replace(variant.parameters[0], default=min(max_value, default), max_value=max_value),
                *(
                    (replace(variant.parameters[1], default=speed_default), *variant.parameters[2:])
                    if len(variant.parameters) > 1
                    else variant.parameters[1:]
                ),
            ),
        )
    if (
        variant
        and variant.layout in {"music_body", "h6076_music_body"}
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
            max_value = ic // 2 if ic < 30 else ceil(ic / 5)
            variant = replace(
                variant,
                parameters=(
                    replace(
                        variant.parameters[0],
                        max_value=max_value,
                        default=min(max_value, ic // 2 if ic < 30 else 7)
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


def music_selector_params_for_mode(mode_code: int, profile: ModelProfile) -> tuple[MusicParamSpec, ...]:
    variant = music_variant(profile, mode_code)
    return variant.selector_parameters if variant is not None else ()


def music_body_params_for_mode(mode_code: int, profile: ModelProfile) -> tuple[MusicParamSpec, ...]:
    variant = music_variant(profile, mode_code)
    if variant is None:
        return ()
    return (
        tuple(
            spec
            for spec in variant.parameters
            if not spec.requires_physical_ic_count or profile.physical_ic_count is not None
        )
        if variant.layout in COMPANION_MUSIC_LAYOUTS and music_parameters_available(profile, variant)
        else ()
    )


def music_params_for_mode(mode_code: int, profile: ModelProfile) -> tuple[MusicParamSpec, ...]:
    return (*music_selector_params_for_mode(mode_code, profile), *music_body_params_for_mode(mode_code, profile))


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


def encode_music_selector_parameters(
    parameters: Mapping[str, int | bool | str], mode_code: int, profile: ModelProfile
) -> dict[str, int]:
    encoded: dict[str, int] = {}
    for spec in music_selector_params_for_mode(mode_code, profile):
        value = parameters[spec.profile_key]
        if spec.kind == "select":
            assert isinstance(value, str)
            encoded[spec.wire_field] = spec.options.index(value)
        else:
            encoded[spec.wire_field] = int(value)
    return encoded


def retained_music_selector_parameters(
    source: object, mode_code: int, profile: ModelProfile
) -> dict[str, int | bool | str]:
    return {
        spec.profile_key: value
        for spec in music_selector_params_for_mode(mode_code, profile)
        if (value := getattr(source, spec.key, None)) is not None
    }


def capture_music_parameters(source: object, profile: ModelProfile, mode: str) -> dict[str, int | bool | str]:
    """New snapshots always carry a mapping; only legacy persisted snapshots omit it."""
    from .music_protocol import music_codebook

    if mode not in profile.music_modes:
        return {}
    mode_code = music_codebook(profile).get(mode)
    if mode_code is None:
        return {}
    selector_parameters = retained_music_selector_parameters(source, mode_code, profile)
    body_parameters = {
        spec.profile_key: getattr(source, spec.key, spec.default)
        for spec in music_body_params_for_mode(mode_code, profile)
    }
    return {**selector_parameters, **body_parameters}
