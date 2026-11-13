"""Explicit DIY family and native mode declarations."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from .const import MODEL_PROFILES
from .effect_catalogue_models import DiyEffectFamily, DiyEffectVariation, NativeModeOption
from .generated_protocol.diy_type03 import DiyType03  # type: ignore[attr-defined]
from .music_protocol import music_codebook
from .protocol_core import H607cDiyBody

# H617A Type04 uploads are selected with DIY code 24.
H617A_TYPE04_APPLY_CODE: Final = 24
DEFAULT_PALETTE: Final = (
    (255, 0, 0),
    (255, 127, 0),
    (255, 255, 0),
    (0, 255, 0),
    (0, 0, 255),
    (0, 255, 255),
    (139, 0, 255),
)


# These basic Type04 families form the base roster.  The family and variation bytes use the structure defined by
# diy_type04.ksy.
H617A_TYPE04_FAMILIES: Final = (
    DiyEffectFamily(
        "fade",
        "Fade",
        0,
        (
            DiyEffectVariation("whole", "Whole strip", 0),
            DiyEffectVariation("sections", "Sections", 1),
            DiyEffectVariation("cycle", "Cycle", 2),
        ),
        True,
    ),
    DiyEffectFamily(
        "jumping",
        "Jumping",
        1,
        (
            DiyEffectVariation("whole", "Whole strip", 0),
            DiyEffectVariation("cycle", "Cycle", 2),
        ),
        True,
    ),
    DiyEffectFamily(
        "blinking",
        "Blinking",
        2,
        (
            DiyEffectVariation("whole", "Whole strip", 0),
            DiyEffectVariation("sections", "Sections", 1),
            DiyEffectVariation("cycle", "Cycle", 2),
        ),
        True,
    ),
    DiyEffectFamily(
        "marquee",
        "Marquee",
        3,
        (
            DiyEffectVariation("all", "Together", 3),
            DiyEffectVariation("gathered", "Gather", 4),
            DiyEffectVariation("dispersive", "Disperse", 5),
        ),
        True,
    ),
    DiyEffectFamily(
        "music",
        "Music",
        4,
        (
            DiyEffectVariation("rhythm", "Rhythm", 8),
            DiyEffectVariation("spectrum", "Spectrum", 6),
            DiyEffectVariation("rolling", "Rolling", 7),
        ),
        False,
        "sensitivity",
    ),
    DiyEffectFamily(
        "stream",
        "Stream",
        8,
        (
            DiyEffectVariation("clockwise", "Clockwise", 9),
            DiyEffectVariation("counter_clockwise", "Counterclockwise", 10),
        ),
        True,
    ),
    DiyEffectFamily(
        "flow",
        "Flow",
        9,
        (
            DiyEffectVariation("clockwise", "Clockwise", 9),
            DiyEffectVariation("counter_clockwise", "Counterclockwise", 10),
        ),
        True,
    ),
    DiyEffectFamily(
        "chase",
        "Chase",
        10,
        (DiyEffectVariation("default", "Default", 0),),
        False,
        palette_max=3,
    ),
)

H617A_PAINTED_EFFECTS: Final = tuple(
    {
        "id": effect.name,
        "label": "Counterclockwise" if effect.name == "counter_clockwise" else effect.name.capitalize(),
    }
    for effect in DiyType03.Effect
)

# Exact H6102 roster.
# The shared A3 grammar does not grant H617A native 501..507 presets.
H6102_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="sensitivity" if family == 4 else "speed",
        rate_min=1,
        multi_rate_min=0,
        palette_max=3 if family == 10 else 8,
        source_reference="H6102 DIY roster",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jump", "Jump", 1, (0, 2)),
        ("blink", "Blink", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("music", "Music", 4, (8, 6, 7)),
    )
)

# H6099 DIY lists.
H6046_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        rate_min=1,
        palette_max=8,
        source_reference="tools/ble/kaitai/speculative/h6046_effect_upload.ksy",
    )
    for name, label, family in (
        ("fade", "Fade", 0),
        ("jumping", "Jumping", 1),
        ("blinking", "Blinking", 2),
        ("breathing", "Breathing", 5),
        ("stream", "Stream", 8),
        ("flow", "Flow", 9),
        ("chase", "Chase", 10),
        ("snow", "Snow", 11),
        ("aurora", "Aurora", 13),
    )
)

H605C_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(DiyEffectVariation(str(variant), variation, variant) for variant, variation in variants),
        mixed,
        rate="sensitivity" if family == 4 else "speed",
        rate_min=1,
        palette_max=3 if family == 10 else 8,
        multi_rate_min=1,
        source_reference="tools/ble/kaitai/speculative/h605c_effect_upload.ksy",
    )
    for name, label, family, mixed, variants in (
        ("fade", "Fade", 0, True, ((0, "Whole strip"), (1, "Sections"), (2, "Cycle"))),
        ("jumping", "Jumping", 1, True, ((0, "Whole strip"), (2, "Cycle"))),
        ("blinking", "Blinking", 2, True, ((0, "Whole strip"), (1, "Sections"), (2, "Cycle"))),
        ("marquee", "Marquee", 3, True, ((3, "Together"), (4, "Gather"), (5, "Disperse"))),
        ("music", "Music", 4, False, ((8, "Rhythm"), (6, "Spectrum"), (7, "Rolling"))),
        ("stream", "Stream", 8, True, ((9, "Clockwise"), (10, "Counterclockwise"))),
        ("flow", "Flow", 9, True, ((9, "Clockwise"), (10, "Counterclockwise"))),
        ("chase", "Chase", 10, False, ((0, "Default"),)),
    )
)

H6099_DIY_APPLY_CODE: Final = 254
H6099_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="none" if family == 4 else "speed",
        rate_min=50 if family == 4 else 1,
        rate_max=50 if family == 4 else 100,
        palette_max=3 if family == 10 else 8,
        source_reference="H6099 basic and mixed DIY lists",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jumping", "Jumping", 1, (0, 2)),
        ("blinking", "Blinking", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("music", "Music", 4, (8, 6, 7)),
    )
)

H6097_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="none" if family == 4 else "speed",
        rate_min=50 if family == 4 else 1,
        rate_max=50 if family == 4 else 100,
        palette_max=3 if family == 10 else 8,
        source_reference="H6097 candidate basic and mixed DIY semantics",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jumping", "Jumping", 1, (0, 2)),
        ("blinking", "Blinking", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("music", "Music", 4, (8, 6, 7)),
    )
)

# H66A0 DIY lists.
H66A0_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="speed",
        rate_min=1,
        rate_max=100,
        palette_max=3 if family == 10 else 8,
        source_reference="H66A0 basic and mixed DIY lists",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jumping", "Jumping", 1, (0, 2)),
        ("blinking", "Blinking", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("fill", "Fill", 37, (0,)),
        ("confrontation", "Confrontation", 38, (0, 1)),
        ("stretch", "Stretch", 39, (0,)),
        ("halo_dyeing", "Halo Dyeing", 40, (0, 1)),
    )
)

# H1A42 DIY lists.
H1A42_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="sensitivity" if family == 4 else "speed",
        rate_min=1,
        rate_max=100,
        multi_rate_min=0,
        palette_max=3 if family == 10 else 8,
        source_reference="H1A42 basic and mixed DIY lists",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jumping", "Jumping", 1, (0, 2)),
        ("blinking", "Blinking", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("music", "Music", 4, (8, 6, 7)),
    )
)

# H61F6 DIY lists.
H61F5_DIY_FAMILIES: Final = tuple(
    replace(
        family,
        source_reference="H61F6 basic and mixed DIY lists",
    )
    for family in H1A42_DIY_FAMILIES
)

H7020_DIY_FAMILIES: Final = (
    DiyEffectFamily(
        "fade",
        "Fade",
        0,
        (
            DiyEffectVariation("1", "Fade 1", 0),
            DiyEffectVariation("2", "Fade 2", 1),
            DiyEffectVariation("3", "Fade 3", 2),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "jumping",
        "Jumping",
        1,
        (
            DiyEffectVariation("4", "Jumping 1", 0),
            DiyEffectVariation("5", "Jumping 2", 2),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "blinking",
        "Blinking",
        2,
        (
            DiyEffectVariation("6", "Blinking 1", 0),
            DiyEffectVariation("7", "Blinking 2", 1),
            DiyEffectVariation("8", "Blinking 3", 2),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "marquee",
        "Marquee",
        3,
        (
            DiyEffectVariation("9", "Marquee 1", 3),
            DiyEffectVariation("10", "Marquee 2", 4),
            DiyEffectVariation("11", "Marquee 3", 5),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "stream",
        "Stream",
        8,
        (
            DiyEffectVariation("12", "Stream 1", 9),
            DiyEffectVariation("13", "Stream 2", 10),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "flow",
        "Flow",
        9,
        (
            DiyEffectVariation("14", "Flow 1", 9),
            DiyEffectVariation("15", "Flow 2", 10),
        ),
        True,
        rate_min=1,
        palette_max=8,
    ),
    DiyEffectFamily(
        "chase",
        "Chase",
        10,
        (DiyEffectVariation("16", "Chase", 0),),
        False,
        rate_min=1,
        palette_max=3,
    ),
)

H7025_DIY_FAMILIES: Final = tuple(
    replace(
        family,
        multi_rate_min=0,
        source_reference="H7025 basic and mixed DIY lists",
    )
    for family in H7020_DIY_FAMILIES[:6]
)

H6072_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"{label} {index + 1}" if len(variants) > 1 else label, variant)
            for index, variant in enumerate(variants)
        ),
        family != 4,
        rate="sensitivity" if family == 4 else "speed",
        palette_max=8,
        source_reference="H6072 candidate basic and mixed DIY parameters",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (1, 0)),
        ("breathe", "Breathe", 5, (1, 0, 2)),
        ("jumping", "Jumping", 1, (2, 0)),
        ("stacking", "Stacking", 24, (0,)),
        ("chase", "Chase", 10, (0,)),
        ("flow", "Flow", 9, (13, 14)),
        ("spray", "Spray", 25, (0,)),
        ("music", "Music", 4, (8, 17, 18, 11, 16)),
    )
)

H6076_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"{label} {index + 1}" if len(variants) > 1 else label, variant)
            for index, variant in enumerate(variants)
        ),
        family != 4,
        rate="sensitivity" if family == 4 else "speed",
        rate_min=1,
        rate_max=100,
        multi_rate_min=1,
        palette_max=8,
        source_reference="H6072 basic and mixed DIY lists",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (1, 0)),
        ("breathe", "Breathe", 5, (1, 0, 2)),
        ("jumping", "Jumping", 1, (2, 0)),
        ("stacking", "Stacking", 24, (0,)),
        ("chase", "Chase", 10, (0,)),
        ("flow", "Flow", 9, (13, 14)),
        ("spray", "Spray", 25, (0,)),
        ("music", "Music", 4, (8, 17, 18, 11, 16)),
    )
)

H600A_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        (DiyEffectVariation("0", label, 0),),
        True,
        rate="speed",
        rate_min=0,
        rate_max=100,
        palette_max=8,
        source_reference="H600A whole-bulb basic and mixed DIY codebook",
    )
    for name, label, family in (
        ("fade", "Fade", 0),
        ("jumping", "Jumping", 1),
        ("blinking", "Blinking", 2),
        ("breathe", "Breathe", 5),
    )
)

H601C_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        (DiyEffectVariation("0", label, 0),),
        True,
        rate="speed",
        rate_min=0,
        rate_max=100,
        palette_max=8,
        source_reference="H601C recessed downlight basic and mixed DIY codebook",
    )
    for name, label, family in (
        ("fade", "Fade", 0),
        ("jumping", "Jumping", 1),
        ("blinking", "Blinking", 2),
        ("breathe", "Breathe", 5),
    )
)


def _mode_label(slug: str) -> str:
    return slug.replace("_", " ").title()


def _native_music_modes(model: str) -> tuple[NativeModeOption, ...]:
    codebook = music_codebook(MODEL_PROFILES[model])
    return tuple(
        NativeModeOption(
            slug,
            _mode_label(slug),
        )
        for slug in MODEL_PROFILES[model].music_modes
        if slug in codebook
    )


H617A_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617A")
H617A_WORKSHOP_APPLY_CODE: Final = 401
H617A_WORKSHOP_SCENE_TYPE: Final = 2
H6179_DIY_SOURCE_REFERENCE: Final = "tools/ble/kaitai/speculative/h6179_diy_body.ksy"
H6199_DIY_SOURCE_REFERENCE: Final = "tools/ble/kaitai/h6199_effect_upload.ksy"
H6199_PALETTE_DIY_APPLY_CODE: Final = 401
H6199_PALETTE_DIY_APPLY_MUSIC_CODE: Final = 2
H6199_WORKSHOP_APPLY_CODE: Final = 402
H6199_WORKSHOP_APPLY_MUSIC_CODE: Final = 0

H6181_DIY_FAMILIES: Final = (
    DiyEffectFamily(
        "fade",
        "Fade",
        0,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference="tools/ble/kaitai/speculative/h6181_diy_body.ksy",
    ),
    DiyEffectFamily(
        "jumping",
        "Jumping",
        1,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference="tools/ble/kaitai/speculative/h6181_diy_body.ksy",
    ),
    DiyEffectFamily(
        "twinkle",
        "Twinkle",
        2,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference="tools/ble/kaitai/speculative/h6181_diy_body.ksy",
    ),
)

H6179_DIY_FAMILIES: Final = (
    DiyEffectFamily(
        "fade",
        "Fade",
        0,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference=H6179_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "jumping",
        "Jumping",
        1,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference=H6179_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "twinkle",
        "Twinkle",
        2,
        (DiyEffectVariation("default", "Default", 0),),
        True,
        source_reference=H6179_DIY_SOURCE_REFERENCE,
    ),
)

H6179_NATIVE_MUSIC_MODES: Final = (
    NativeModeOption("mode_0", "Mode 1"),
    NativeModeOption("mode_1", "Mode 2"),
)
H7020_NATIVE_MUSIC_MODES: Final = _native_music_modes("H7020")

H6199_PALETTE_DIY_FAMILIES: Final = (
    DiyEffectFamily(
        "fade",
        "Fade",
        0,
        (DiyEffectVariation("default", "Default", 0),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "jumping",
        "Jumping",
        1,
        (DiyEffectVariation("default", "Default", 0),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "twinkle",
        "Twinkle",
        2,
        (DiyEffectVariation("default", "Default", 0),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "marquee",
        "Marquee",
        3,
        (DiyEffectVariation("default", "Default", 3),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "music",
        "Music",
        4,
        (DiyEffectVariation("default", "Default", 8),),
        False,
        "sensitivity",
        H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "chasing",
        "Chasing",
        8,
        (
            DiyEffectVariation("clockwise", "Clockwise", 9),
            DiyEffectVariation("counter_clockwise", "Counterclockwise", 10),
        ),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "rainbow",
        "Rainbow",
        9,
        (DiyEffectVariation("default", "Default", 9),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
    DiyEffectFamily(
        "crossing",
        "Crossing",
        10,
        (DiyEffectVariation("default", "Default", 0),),
        False,
        source_reference=H6199_DIY_SOURCE_REFERENCE,
    ),
)

H6199_NATIVE_MUSIC_MODES: Final = _native_music_modes("H6199")


def _native_video_modes(model: str) -> tuple[NativeModeOption, ...]:
    return tuple(NativeModeOption(mode, mode.replace("_", " ").title()) for mode in MODEL_PROFILES[model].video_modes)


H6199_VIDEO_MODES: Final = _native_video_modes("H6199")
H617E_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617E")

H6125_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        name,
        label,
        family,
        tuple(
            DiyEffectVariation(str(variant), f"Variation {index + 1}", variant)
            for index, variant in enumerate(variants)
        ),
        family in (0, 1, 2, 3, 8, 9),
        rate="sensitivity" if family == 4 else "speed",
        rate_min=1,
        multi_rate_min=0,
        palette_max=3 if family == 10 else 8,
        source_reference="H6125 DreamColor basic and mixed DIY",
    )
    for name, label, family, variants in (
        ("fade", "Fade", 0, (0, 1, 2)),
        ("jump", "Jump", 1, (0, 2)),
        ("blink", "Blink", 2, (0, 1, 2)),
        ("marquee", "Marquee", 3, (3, 4, 5)),
        ("stream", "Stream", 8, (9, 10)),
        ("flow", "Flow", 9, (9, 10)),
        ("chase", "Chase", 10, (0,)),
        ("music", "Music", 4, (8, 6, 7)),
    )
)
H6125_NATIVE_MUSIC_MODES: Final = _native_music_modes("H6125")
H6117_NATIVE_MUSIC_MODES: Final = _native_music_modes("H6117")
H6117_DIY_FAMILIES: Final = tuple(
    replace(family, source_reference="H6117 DreamColor basic and mixed DIY compatibility")
    for family in H6125_DIY_FAMILIES
)
H617C_DIY_FAMILIES: Final = tuple(
    replace(family, source_reference="H617C DreamColor basic and mixed DIY") for family in H6125_DIY_FAMILIES
)
H617C_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617C")
H619A_DIY_FAMILIES: Final = tuple(
    replace(family, source_reference="H619A RGBIC basic and mixed DIY") for family in H6125_DIY_FAMILIES
)
H619A_NATIVE_MUSIC_MODES: Final = _native_music_modes("H619A")
# The selector order follows the product UI, not the wire codes.
H6076_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H6076"].music_modes
)
H6072_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H6072"].music_modes
)
H607C_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H607C"].music_modes
)


H607C_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        id=kind.name,
        label=label,
        family=int(kind),
        variations=tuple(
            DiyEffectVariation(f"variation_{int(variant)}", f"Variation {index + 1}", int(variant))
            for index, variant in enumerate(variants)
        ),
        supports_multi=True,
        source_reference="H607C candidate native zone parameters",
        rate_min=50 if kind == H607cDiyBody.Family.drip else 0,
        rate_max=50 if kind == H607cDiyBody.Family.drip else 100,
        palette_min=bounds[0],
        palette_max=bounds[1],
        secondary_palette_min=secondary[0] if secondary else None,
        secondary_palette_max=secondary[1] if secondary else None,
        palette_labels=("Background", "Accent colours")
        if kind == H607cDiyBody.Family.shimmer
        else ("Moving colours", "Breathing colours")
        if kind == H607cDiyBody.Family.drip
        else None,
    )
    for kind, label, variants, bounds, secondary in (
        (
            H607cDiyBody.Family.gradual,
            "Gradual",
            (H607cDiyBody.Variant.native_89, H607cDiyBody.Variant.native_88),
            (2, 8),
            None,
        ),
        (
            H607cDiyBody.Family.breathe,
            "Breathe",
            (H607cDiyBody.Variant.native_89, H607cDiyBody.Variant.native_88),
            (2, 8),
            None,
        ),
        (
            H607cDiyBody.Family.stream,
            "Flow",
            (H607cDiyBody.Variant.native_13, H607cDiyBody.Variant.native_14),
            (2, 8),
            None,
        ),
        (H607cDiyBody.Family.colour_wall, "Colour wall", (H607cDiyBody.Variant.primary,), (2, 8), None),
        (H607cDiyBody.Family.shimmer, "Shimmer", (H607cDiyBody.Variant.primary,), (1, 1), (1, 8)),
        (H607cDiyBody.Family.chase, "Chase", (H607cDiyBody.Variant.primary,), (2, 8), None),
        (
            H607cDiyBody.Family.shock,
            "Flash",
            (H607cDiyBody.Variant.native_89, H607cDiyBody.Variant.native_88),
            (1, 8),
            None,
        ),
        (H607cDiyBody.Family.drip, "Drip", (H607cDiyBody.Variant.primary,), (1, 8), (2, 8)),
        (H607cDiyBody.Family.lava, "Lava", (H607cDiyBody.Variant.primary,), (3, 8), None),
    )
)


H7025_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H7025"].music_modes
)

H60A1_DIY_FAMILIES: Final = tuple(
    replace(family, palette_max=8, source_reference="H60A1")
    for family in H617A_TYPE04_FAMILIES
    if family.family in (0, 1, 2, 3, 8, 9, 10)
)


H60B2_DIY_FAMILIES: Final = tuple(
    DiyEffectFamily(
        id=name,
        label=name.replace("_", " ").capitalize(),
        family=kind,
        variations=(
            (DiyEffectVariation("up", "Up", 13), DiyEffectVariation("down", "Down", 14))
            if kind in (4, 6, 7)
            else (DiyEffectVariation("default", "Default", 0),)
        ),
        supports_multi=False,
        rate_min=1,
        palette_min=1 if kind in (1, 3, 9) else 2,
        palette_max=8,
        source_reference="H60B2 candidate native palette contract",
    )
    for kind, name in enumerate(
        ("fade", "breathe", "jump", "blink", "chase", "shimmer", "bloom", "stream", "colour_wall", "drip")
    )
)
