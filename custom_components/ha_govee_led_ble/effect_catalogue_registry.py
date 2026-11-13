"""Complete explicit Effect Studio catalogues for each model."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from .effect_catalogue_families import (
    DEFAULT_PALETTE,
    H1A42_DIY_FAMILIES,
    H60B2_DIY_FAMILIES,
    H61F5_DIY_FAMILIES,
    H66A0_DIY_FAMILIES,
    H600A_DIY_FAMILIES,
    H601C_DIY_FAMILIES,
    H605C_DIY_FAMILIES,
    H607C_DIY_FAMILIES,
    H607C_NATIVE_MUSIC_MODES,
    H617A_NATIVE_MUSIC_MODES,
    H617A_PAINTED_EFFECTS,
    H617A_TYPE04_FAMILIES,
    H617C_DIY_FAMILIES,
    H617C_NATIVE_MUSIC_MODES,
    H617E_NATIVE_MUSIC_MODES,
    H619A_DIY_FAMILIES,
    H619A_NATIVE_MUSIC_MODES,
    H6046_DIY_FAMILIES,
    H6072_DIY_FAMILIES,
    H6072_NATIVE_MUSIC_MODES,
    H6076_DIY_FAMILIES,
    H6076_NATIVE_MUSIC_MODES,
    H6097_DIY_FAMILIES,
    H6099_DIY_FAMILIES,
    H6102_DIY_FAMILIES,
    H6117_DIY_FAMILIES,
    H6117_NATIVE_MUSIC_MODES,
    H6125_DIY_FAMILIES,
    H6125_NATIVE_MUSIC_MODES,
    H6179_DIY_FAMILIES,
    H6179_NATIVE_MUSIC_MODES,
    H6181_DIY_FAMILIES,
    H6199_NATIVE_MUSIC_MODES,
    H6199_PALETTE_DIY_FAMILIES,
    H6199_VIDEO_MODES,
    H7020_DIY_FAMILIES,
    H7020_NATIVE_MUSIC_MODES,
    H7025_DIY_FAMILIES,
    H7025_NATIVE_MUSIC_MODES,
    _native_music_modes,
    _native_video_modes,
)
from .effect_catalogue_models import CatalogueTemplate, ModelEffectCatalogue, NativeModeOption
from .effect_catalogue_templates import (
    H617A_CATALOGUE_TEMPLATES,
    H617C_NATIVE_DIY_TEMPLATES,
    H617E_CATALOGUE_TEMPLATES,
    H619A_NATIVE_DIY_TEMPLATES,
    H6102_NATIVE_DIY_TEMPLATES,
    H6117_NATIVE_DIY_TEMPLATES,
    H6125_NATIVE_DIY_TEMPLATES,
    H6179_CATALOGUE_TEMPLATES,
    H6199_CATALOGUE_TEMPLATES,
    H7020_CATALOGUE_TEMPLATES,
    H7020_NATIVE_DIY_CONTRACTS,
    H7025_CATALOGUE_TEMPLATES,
    _ceiling_catalogue,
    _h60b0_templates,
    _h607c_templates,
    _h1771_templates,
    _music_template,
    _single_template,
    _video_template,
)
from .effect_domain import NativeEffect, PaintedEffect
from .music_semantics import H60B0_ZONE_MUSIC_MODES
from .native_effect import NativeDiyLayer
from .protocol_core import H607cDiyBody, H607cPaintBody

MODEL_EFFECT_CATALOGUES: Final = {
    "H60B2": ModelEffectCatalogue(
        sku="H60B2",
        painted_effects=(),
        effects=H60B2_DIY_FAMILIES,
        music_modes=_native_music_modes("H60B2"),
        video_modes=(),
        templates=(
            *(
                CatalogueTemplate(
                    id=f"template:native-diy:{family.id}",
                    label=family.label,
                    category="single-layer",
                    rate_min=1,
                    content=NativeEffect(
                        model="H60B2",
                        family=803,
                        layers=(
                            NativeDiyLayer(
                                kind=family.family,
                                speed=50,
                                palette=DEFAULT_PALETTE,
                                parameter=family.variations[0].variant,
                            ),
                        ),
                    ),
                )
                for family in H60B2_DIY_FAMILIES
            ),
            *(_music_template("H60B2", mode) for mode in _native_music_modes("H60B2")),
        ),
        workshop_templates=(),
        native_zones=(("heads", 3, 3),),
        temporary_diy_selector=254,
    ),
    "H60B0": ModelEffectCatalogue(
        sku="H60B0",
        native_zones=(("side", 8, None), ("ripple", 1, None)),
        music_zone_modes=H60B0_ZONE_MUSIC_MODES,
        auxiliary_music_modes=("vortex", "disabled"),
        painted_effects=(),
        effects=(),
        music_modes=(
            *_native_music_modes("H60B0"),
            NativeModeOption("vortex", "Vortex"),
            NativeModeOption("disabled", "Off"),
        ),
        video_modes=(),
        templates=(*_h60b0_templates(), *(_music_template("H60B0", mode) for mode in _native_music_modes("H60B0"))),
        workshop_templates=(),
        advanced_create=False,
        temporary_diy_selector=254,
    ),
    "H605C": ModelEffectCatalogue(
        sku="H605C",
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H605C_DIY_FAMILIES,
        music_modes=_native_music_modes("H605C"),
        video_modes=_native_video_modes("H605C"),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Paint",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), background=(255, 255, 255), addressing="physical_ic"),
            ),
            *(_single_template("H605C", family) for family in H605C_DIY_FAMILIES),
            *(_music_template("H605C", mode) for mode in _native_music_modes("H605C")),
            *(_video_template("H605C", mode) for mode in _native_video_modes("H605C")),
        ),
        workshop_templates=(),
        diy_slot_policy="approved_observed",
    ),
    "H1771": ModelEffectCatalogue(
        sku="H1771",
        painted_effects=(),
        effects=(),
        music_modes=_native_music_modes("H1771"),
        video_modes=(),
        templates=(*_h1771_templates(), *(_music_template("H1771", mode) for mode in _native_music_modes("H1771"))),
        workshop_templates=(),
        temporary_diy_selector=254,
        advanced_create=False,
    ),
    "H6046": ModelEffectCatalogue(
        sku="H6046",
        painted_effects=(),
        effects=H6046_DIY_FAMILIES,
        music_modes=_native_music_modes("H6046"),
        video_modes=(),
        templates=(
            *(_single_template("H6046", family) for family in H6046_DIY_FAMILIES),
            *(_music_template("H6046", mode) for mode in _native_music_modes("H6046")),
        ),
        workshop_templates=(),
        speed_min=1,
        multi_max=4,
        diy_slot_policy="approved_observed",
    ),
    "H60A1": _ceiling_catalogue("H60A1"),
    "H60A6": _ceiling_catalogue("H60A6"),
    "H6102": ModelEffectCatalogue(
        sku="H6102",
        native_diy_palette_groups=(
            (501, (0,), 1, 1),
            (501, (1, 2), 4, 8),
            (502, (0, 1), 2, 8),
            (504, (0, 1, 2), 3, 8),
            (505, (1,), 1, 1),
            (506, (0, 1), 2, 8),
            (506, (2, 3), 2, 8),
        ),
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6102_DIY_FAMILIES,
        music_modes=_native_music_modes("H6102"),
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise", speed=50, brightness=100, segments=(None,), addressing="physical_ic"
                ),
            ),
            *(_single_template("H6102", family) for family in H6102_DIY_FAMILIES),
            *(_music_template("H6102", mode) for mode in _native_music_modes("H6102")),
            *H6102_NATIVE_DIY_TEMPLATES,
        ),
        workshop_templates=(),
    ),
    "H6097": ModelEffectCatalogue(
        sku="H6097",
        temporary_diy_selector=254,
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6097_DIY_FAMILIES,
        music_modes=_native_music_modes("H6097"),
        video_modes=_native_video_modes("H6097"),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Graffiti",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), background=(255, 255, 255), addressing="physical_ic"),
            ),
            *(_single_template("H6097", family) for family in H6097_DIY_FAMILIES),
            *(_music_template("H6097", mode) for mode in _native_music_modes("H6097")),
            *(_video_template("H6097", mode, saturation=100) for mode in _native_video_modes("H6097")),
        ),
        workshop_templates=(),
    ),
    "H6099": ModelEffectCatalogue(
        sku="H6099",
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6099_DIY_FAMILIES,
        music_modes=_native_music_modes("H6099"),
        video_modes=_native_video_modes("H6099"),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Graffiti",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), background=(255, 255, 255), addressing="physical_ic"),
            ),
            *(_single_template("H6099", family) for family in H6099_DIY_FAMILIES),
            *(_music_template("H6099", mode) for mode in _native_music_modes("H6099")),
            *(_video_template("H6099", mode, saturation=100) for mode in _native_video_modes("H6099")),
        ),
        workshop_templates=(),
    ),
    "H66A0": ModelEffectCatalogue(
        sku="H66A0",
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H66A0_DIY_FAMILIES,
        music_modes=_native_music_modes("H66A0"),
        video_modes=_native_video_modes("H66A0"),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Graffiti",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), background=(255, 255, 255), addressing="physical_ic"),
            ),
            *(_single_template("H66A0", family) for family in H66A0_DIY_FAMILIES),
            *(_music_template("H66A0", mode) for mode in _native_music_modes("H66A0")),
            *(_video_template("H66A0", mode, saturation=100) for mode in _native_video_modes("H66A0")),
        ),
        workshop_templates=(),
    ),
    "H1A42": ModelEffectCatalogue(
        sku="H1A42",
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H1A42_DIY_FAMILIES,
        music_modes=_native_music_modes("H1A42"),
        video_modes=(),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Graffiti",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), addressing="physical_ic"),
            ),
            *(_single_template("H1A42", family) for family in H1A42_DIY_FAMILIES),
            *(_music_template("H1A42", mode) for mode in _native_music_modes("H1A42")),
        ),
        workshop_templates=(),
    ),
    "H61F5": ModelEffectCatalogue(
        sku="H61F5",
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H61F5_DIY_FAMILIES,
        music_modes=_native_music_modes("H61F5"),
        video_modes=(),
        templates=(
            CatalogueTemplate(
                "template:paint",
                "Graffiti",
                "single-layer",
                PaintedEffect("clockwise", 50, 100, (None,), addressing="physical_ic"),
            ),
            *(_single_template("H61F5", family) for family in H61F5_DIY_FAMILIES),
            *(_music_template("H61F5", mode) for mode in _native_music_modes("H61F5")),
        ),
        workshop_templates=(),
    ),
    "H6117": ModelEffectCatalogue(
        sku="H6117",
        native_diy_palette_groups=(
            (501, (0,), 1, 1),
            (501, (1, 2), 4, 8),
            (502, (0, 1), 2, 8),
            (504, (0, 1, 2), 3, 8),
            (505, (1,), 1, 1),
            (506, (0, 1), 2, 8),
            (506, (2, 3), 2, 8),
        ),
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6117_DIY_FAMILIES,
        music_modes=H6117_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise",
                    speed=50,
                    brightness=100,
                    segments=(None,),
                    addressing="physical_ic",
                ),
            ),
            *(_single_template("H6117", family) for family in H6117_DIY_FAMILIES),
            *(_music_template("H6117", mode) for mode in H6117_NATIVE_MUSIC_MODES),
            *H6117_NATIVE_DIY_TEMPLATES,
        ),
        workshop_templates=(),
    ),
    "H6125": ModelEffectCatalogue(
        sku="H6125",
        native_diy_palette_groups=(
            (501, (0,), 1, 1),
            (501, (1, 2), 4, 8),
            (502, (0, 1), 2, 8),
            (504, (0, 1, 2), 3, 8),
            (505, (1,), 1, 1),
            (506, (0, 1), 2, 8),
            (506, (2, 3), 2, 8),
        ),
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6125_DIY_FAMILIES,
        music_modes=H6125_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise", speed=50, brightness=100, segments=(None,), addressing="physical_ic"
                ),
            ),
            *(_single_template("H6125", family) for family in H6125_DIY_FAMILIES),
            *(_music_template("H6125", mode) for mode in H6125_NATIVE_MUSIC_MODES),
            *H6125_NATIVE_DIY_TEMPLATES,
        ),
        workshop_templates=(),
    ),
    "H617A": ModelEffectCatalogue(
        sku="H617A",
        painted_effects=H617A_PAINTED_EFFECTS,
        effects=H617A_TYPE04_FAMILIES,
        music_modes=H617A_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H617A_CATALOGUE_TEMPLATES,
        workshop_templates=(),
    ),
    "H617C": ModelEffectCatalogue(
        sku="H617C",
        native_diy_palette_groups=(
            (501, (0,), 1, 1),
            (501, (1, 2), 4, 8),
            (502, (0, 1), 2, 8),
            (504, (0, 1, 2), 3, 8),
            (505, (1,), 1, 1),
            (506, (0, 1), 2, 8),
            (506, (2, 3), 2, 8),
        ),
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H617C_DIY_FAMILIES,
        music_modes=H617C_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise", speed=50, brightness=100, segments=(None,), addressing="physical_ic"
                ),
            ),
            *(_single_template("H617C", family) for family in H617C_DIY_FAMILIES),
            *(_music_template("H617C", mode) for mode in H617C_NATIVE_MUSIC_MODES),
            *H617C_NATIVE_DIY_TEMPLATES,
        ),
        workshop_templates=(),
    ),
    "H617E": ModelEffectCatalogue(
        sku="H617E",
        painted_effects=H617A_PAINTED_EFFECTS,
        effects=tuple(replace(family, palette_max=None) for family in H617A_TYPE04_FAMILIES),
        music_modes=H617E_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H617E_CATALOGUE_TEMPLATES,
        workshop_templates=(),
    ),
    "H6181": ModelEffectCatalogue(
        sku="H6181",
        painted_effects=(),
        effects=H6181_DIY_FAMILIES,
        music_modes=tuple(NativeModeOption(mode, mode.title()) for mode in ("dynamic", "soft", "bloom", "radiant")),
        video_modes=(),
        templates=(
            *(_single_template("H6181", family) for family in H6181_DIY_FAMILIES),
            *(
                _music_template("H6181", NativeModeOption(mode, mode.title()))
                for mode in ("dynamic", "soft", "bloom", "radiant")
            ),
        ),
        workshop_templates=(),
        diy_slot_policy="approved_observed",
    ),
    "H6179": ModelEffectCatalogue(
        sku="H6179",
        painted_effects=(),
        effects=H6179_DIY_FAMILIES,
        music_modes=H6179_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H6179_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        diy_slot_policy="approved_observed",
    ),
    "H619A": ModelEffectCatalogue(
        sku="H619A",
        native_diy_palette_groups=(
            (501, (0,), 1, 1),
            (501, (1, 2), 4, 8),
            (502, (0, 1), 2, 8),
            (504, (0, 1, 2), 3, 8),
            (505, (1,), 1, 1),
            (506, (0, 1), 2, 8),
            (506, (2, 3), 2, 8),
        ),
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H619A_DIY_FAMILIES,
        music_modes=H619A_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise", speed=50, brightness=100, segments=(None,) * 20, addressing="physical_ic"
                ),
            ),
            *(_single_template("H619A", family) for family in H619A_DIY_FAMILIES),
            *(_music_template("H619A", mode) for mode in H619A_NATIVE_MUSIC_MODES),
            *H619A_NATIVE_DIY_TEMPLATES,
        ),
        workshop_templates=(),
    ),
    "H6199": ModelEffectCatalogue(
        sku="H6199",
        painted_effects=(),
        effects=H6199_PALETTE_DIY_FAMILIES,
        music_modes=H6199_NATIVE_MUSIC_MODES,
        video_modes=H6199_VIDEO_MODES,
        templates=H6199_CATALOGUE_TEMPLATES,
        workshop_templates=(),
    ),
    "H6072": ModelEffectCatalogue(
        sku="H6072",
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6072_DIY_FAMILIES,
        music_modes=H6072_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise",
                    speed=50,
                    brightness=100,
                    segments=(None,),
                    background=(255, 255, 255),
                    addressing="physical_ic",
                ),
            ),
            *(_single_template("H6072", family) for family in H6072_DIY_FAMILIES),
            *(_music_template("H6072", mode) for mode in H6072_NATIVE_MUSIC_MODES),
        ),
        workshop_templates=(),
        diy_slot_policy="approved_observed",
    ),
    "H607C": ModelEffectCatalogue(
        sku="H607C",
        painted_addressing="physical_ic",
        painted_effects=tuple(
            {"id": direction.name, "label": direction.name.replace("_", " ").capitalize()}
            for direction in H607cPaintBody.Direction
        ),
        effects=H607C_DIY_FAMILIES,
        music_modes=H607C_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=_h607c_templates(),
        workshop_templates=(),
        multi_max=2,
        temporary_diy_selector=int(H607cDiyBody.ActivationSelector.temporary),
        advanced_create=False,
    ),
    "H6076": ModelEffectCatalogue(
        sku="H6076",
        painted_addressing="physical_ic",
        painted_background=(255, 255, 255),
        painted_effects=tuple(
            {"id": name, "label": name.replace("_", " ").capitalize()}
            for name in ("clockwise", "counter_clockwise", "cycle", "gradient", "twinkle", "breathe")
        ),
        effects=H6076_DIY_FAMILIES,
        music_modes=H6076_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=(
            CatalogueTemplate(
                id="template:paint",
                label="Paint",
                category="single-layer",
                content=PaintedEffect(
                    effect="clockwise",
                    speed=50,
                    brightness=100,
                    segments=(None,),
                    background=(255, 255, 255),
                    addressing="physical_ic",
                ),
            ),
            *(_single_template("H6076", family) for family in H6076_DIY_FAMILIES),
            *(_music_template("H6076", mode) for mode in H6076_NATIVE_MUSIC_MODES),
        ),
        workshop_templates=(),
        brightness_min=1,
    ),
    "H7020": ModelEffectCatalogue(
        sku="H7020",
        painted_effects=(),
        effects=H7020_DIY_FAMILIES,
        music_modes=H7020_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H7020_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        native_diy_templates=H7020_NATIVE_DIY_CONTRACTS,
        diy_slot_policy="approved_observed",
        advanced_create=False,
        speed_min=1,
    ),
    "H7025": ModelEffectCatalogue(
        sku="H7025",
        painted_effects=(),
        effects=H7025_DIY_FAMILIES,
        music_modes=H7025_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H7025_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        diy_slot_policy="approved_observed",
        advanced_create=False,
    ),
    "H600A": ModelEffectCatalogue(
        sku="H600A",
        painted_effects=(),
        effects=H600A_DIY_FAMILIES,
        music_modes=(),
        video_modes=(),
        templates=tuple(_single_template("H600A", family) for family in H600A_DIY_FAMILIES),
        workshop_templates=(),
        advanced_create=False,
        diy_slot_policy="approved_observed",
    ),
    "H601C": ModelEffectCatalogue(
        sku="H601C",
        painted_effects=(),
        effects=H601C_DIY_FAMILIES,
        music_modes=(),
        video_modes=(),
        templates=tuple(_single_template("H601C", family) for family in H601C_DIY_FAMILIES),
        workshop_templates=(),
        advanced_create=False,
    ),
}
