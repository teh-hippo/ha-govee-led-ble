"""Effect Studio template construction and native preset seeds."""

from __future__ import annotations

import base64
from dataclasses import replace
from typing import Final

from .const import MODEL_PROFILES, get_profile
from .effect_catalogue_families import (
    DEFAULT_PALETTE,
    H60A1_DIY_FAMILIES,
    H607C_DIY_FAMILIES,
    H607C_NATIVE_MUSIC_MODES,
    H617A_NATIVE_MUSIC_MODES,
    H617A_TYPE04_FAMILIES,
    H617E_NATIVE_MUSIC_MODES,
    H6179_DIY_FAMILIES,
    H6179_NATIVE_MUSIC_MODES,
    H6199_NATIVE_MUSIC_MODES,
    H6199_PALETTE_DIY_FAMILIES,
    H6199_VIDEO_MODES,
    H7020_DIY_FAMILIES,
    H7020_NATIVE_MUSIC_MODES,
    H7025_DIY_FAMILIES,
    _native_music_modes,
)
from .effect_catalogue_models import (
    CatalogueTemplate,
    DiyEffectFamily,
    ModelEffectCatalogue,
    NativeDiyTemplateContract,
    NativeModeOption,
    WorkshopTemplate,
)
from .effect_domain import (
    EffectContent,
    H6179SingleDiyEffect,
    LayeredEffect,
    MusicProfile,
    NativeEffect,
    PaintedEffect,
    PaletteDiyEffect,
    RelativeBrightness,
    SingleEffect,
    VideoProfile,
)
from .h60a6_effects import native_diy_preset
from .layered_scene_decoder import decode_workshop_effect
from .music_commands import default_music_zones
from .music_protocol import music_code_for
from .music_semantics import music_variant
from .native_effect import NativeDiyLayer
from .protocol_core import H60a6PaintBody, H607cDiyBody, H607cPaintBody, H1771DiyBody


def _single_template(
    model: str,
    family: DiyEffectFamily,
    *,
    grammar: str | None = None,
) -> CatalogueTemplate:
    variation = family.variations[0]
    content: EffectContent
    grammar = get_profile(model).effect_grammar if grammar is None else grammar
    if grammar in {"H6046", "H617A", "H6099", "H6181"}:
        content = SingleEffect(
            family=family.family,
            variant=variation.variant,
            speed=50,
            palette=((255, 0, 0), (0, 255, 0), (0, 0, 255)) if family.palette_max == 3 else DEFAULT_PALETTE,
        )
    elif grammar == "H6179":
        content = H6179SingleDiyEffect(
            model=model,
            family=family.family,
            variant=variation.variant,
            speed=50,
            palette=DEFAULT_PALETTE,
        )
    elif grammar == "H6199":
        content = PaletteDiyEffect(
            model=model,
            family=family.family,
            variant=variation.variant,
            speed=50,
            palette=DEFAULT_PALETTE,
        )
    else:
        raise ValueError(f"{model} has no supported single-effect grammar")
    return CatalogueTemplate(
        id=f"template:single:{family.family}:{variation.variant}",
        label=family.label,
        category="single-layer",
        content=content,
    )


def _music_template(model: str, mode: NativeModeOption) -> CatalogueTemplate:
    profile = MODEL_PROFILES[model]
    variant = music_variant(profile, music_code_for(model, mode.id, profile=profile))
    return CatalogueTemplate(
        id=f"template:music:{mode.id}",
        label=mode.label,
        category="music",
        content=MusicProfile(
            model=model,
            mode=mode.id,
            sensitivity=profile.music_sensitivity_max,
            colour=None,
            calm=variant.calm_default if variant and variant.supports_style else None,
            parameters={},
            zones=default_music_zones(profile, mode.id),
        ),
    )


def _video_template(model: str, mode: NativeModeOption, *, saturation: int = 50) -> CatalogueTemplate:
    profile = MODEL_PROFILES[model]
    return CatalogueTemplate(
        id=f"template:video:{mode.id}",
        label=mode.label,
        category="video",
        content=VideoProfile(
            model=model,
            mode=mode.id,
            full_screen=True if profile.supports_video_capture_region else None,
            saturation=saturation if profile.supports_video_saturation else None,
            sound_effects=False if profile.supports_video_sound_effects else None,
            sound_effects_softness=50 if profile.supports_video_sound_effects else None,
            white_balance_position=(
                profile.video_white_balance_default
                if profile.supports_white_balance and profile.video_white_balance_representation == "position"
                else None
            ),
            white_balance_value=(
                profile.video_white_balance_default
                if profile.supports_white_balance and profile.video_white_balance_representation == "scalar"
                else None
            ),
            relative_brightness=(
                RelativeBrightness(**dict.fromkeys(profile.video_brightness_zones, 100))
                if profile.supports_relative_brightness or profile.video_embeds_relative_brightness
                else None
            ),
            blank_screen=False if profile.supports_blank_screen else None,
        ),
    )


def _h617a_catalogue_templates(
    model: str,
    music_modes: tuple[NativeModeOption, ...],
) -> tuple[CatalogueTemplate, ...]:
    return (
        CatalogueTemplate(
            id="template:paint",
            label="Paint",
            category="single-layer",
            content=PaintedEffect(
                effect="clockwise",
                speed=50,
                brightness=100,
                segments=(None,) * MODEL_PROFILES[model].segment_count,
            ),
        ),
        *(
            _single_template(model, family if model == "H617A" else replace(family, palette_max=None))
            for family in H617A_TYPE04_FAMILIES
        ),
        *(_music_template(model, mode) for mode in music_modes),
    )


# Native DIY seeds, in selector order.
# Seed IC quantities are opaque preset values, never device geometry metadata.
H617A_NATIVE_DIY_SEEDS: Final = (
    (
        501,
        "Brilliant / Colorful",
        "AxoAAAABAAEyMgEAAAAC+gABAP8AAAAAAAAAAB0AAgoFAAH/MgHIAAAC+goC/38AAAD/AAAAAAAAARoAAh4KAAH/MgHIAAAB+goB8v8AAAAAAAAAAg==",
    ),
    (502, "Colorful Sky", "AhoAAg8BAAH/AAHIMjICyDIBAAD/AAAAAAAAARoAAg8BAAH/MgHIFBQCyDIB/wAAAAAAAAAAAA=="),
    (503, "Meteor", "ASAgAQAKAgH/CgIAAAACAAADAKr/AP//////AAD6EAH+AA=="),
    (
        504,
        "Meteor Shower",
        "AyAgAQAKAgH/CgIAAAAA+mQD/wAAAAD//3v/AAD6EAH9ABokAQAKAgH/CgIAAAAA+mQBAP8AAAD6EAH9ABonAQAKAgH/CgIAAAAA+mQB9QD/AAD6EAH9AA==",
    ),
    (505, "Shine", "AiYAAhQKAgH/yADwAAAB8AAF/wAA/////wAAAP8AAAD/AAD/EAHwARoAAQAAAAEUFAAAAAAAADIBAAAAAAAAAAAAAA=="),
    (
        506,
        "Bloom DIY",
        "BCkAAg8FAAH/AAL/MjIC/wIG/wAAAAAA//8AAAAAAAD/AP//AAAAEgH6ACkAAg8FAAH/AAL/MjIC/wIGiwD/AAAA//8AAAAA/3L/AP//AAAAEgH6AB1QAQAZAAH/AAD/MjICZAACAP///38AFAD/AAAAAB1VAQAZAAH/AAD/MjICZAAC/wAAAAD/FgD/AAAAAA==",
    ),
    (507, "Stack", "AiAAAAABAAFkZAAAAAAAyDID/wAAAP8AAAD/FgDOAAAAASAAAQABAAFkZAAAAAAAyDIDAAD//wAAAP8AFAD/AAAAAA=="),
)
H617A_NATIVE_DIY_TEMPLATES: Final = tuple(
    CatalogueTemplate(
        id=f"template:native-diy:{code}",
        label=label,
        category="advanced",
        content=replace(decode_workshop_effect("H617A", base64.b64decode(seed))[0], native_diy=code),
    )
    for code, label, seed in H617A_NATIVE_DIY_SEEDS
)

H7020_NATIVE_DIY_SEEDS: Final = (
    (
        17,
        89,
        "Spin 1",
        "BSYgAAABAgH/fgOACgoA8xQF/4wH//4HYf4IB/6uB7r+FQD4AACAACkiAAABAgH/GAOACgoA8xQG/4wH//4H/14H/wY9/wbTtAb+FwD4AACAACkkAAABAgH/GQOACgoA8hQG/4wH//4HCP+qBtr+CH3+1wb/FQD4AACAACkmAAABAgH/GQOACgoA8xQG/4wH//4H/waF9Qf/Vmb/B6L/FwD4AACAACkoAAABAgH/GQOACgoA8xQG/4wH//4H8VD/B2n/CP+RCP8PFQD4AACAAA==",
    ),
    (
        18,
        89,
        "Spin 2",
        "BSYgAAABAgH/fgOACgoA8xQF/4wH//4HYf4IB/6uB7r+FwD4AACAACkiAAABAgH/GAOACgoA8xQG/4wH//4H/14H/wY9/wbTtAb+FQD4AACAACkkAAABAgH/GQOACgoA8hQG/4wH//4HCP+qBtr+CH3+1wb/FwD4AACAACkmAAABAgH/GQOACgoA8xQG/4wH//4H/waF9Qf/Vmb/B6L/FQD4AACAACkoAAABAgH/GQOACgoA8xQG/4wH//4H8VD/B2n/CP+RCP8PFwD4AACAAA==",
    ),
    (
        19,
        90,
        "Ribbon",
        "Ai8AAgoFAgL/GQDZAAD/GQDdAAAC+AoG/zgA/38A//8AAP8AAP//AAD/AACAAAAABCkAAAABAAHEdACbFBQA+AoG/w8H/38A//8AAP8AAP//AAD/AACAAACAAQ==",
    ),
)

H7020_NATIVE_DIY_CONTRACTS: Final = (
    NativeDiyTemplateContract(17, 89, 2, 5, 1, 8, "selected_movement_speed", 150, 250, 248),
    NativeDiyTemplateContract(18, 89, 2, 5, 1, 8, "selected_movement_speed", 150, 250, 248),
    NativeDiyTemplateContract(19, 90, 2, 2, 1, 8, "colour_brightness_speed", 150, 253, 202),
)


def _h7020_native_diy_content(template_id: int, seed: str) -> LayeredEffect:
    content = replace(decode_workshop_effect("H617A", base64.b64decode(seed))[0], native_diy=template_id)
    if template_id != 19:
        return content
    return replace(
        content,
        layers=tuple(
            replace(
                layer,
                colour_speed=202,
                brightness_patterns=tuple(replace(pattern, change_speed=202) for pattern in layer.brightness_patterns),
            )
            for layer in content.layers
        ),
    )


H7020_NATIVE_DIY_TEMPLATES: Final = tuple(
    CatalogueTemplate(
        id=f"template:native-diy:{template_id}",
        label=label,
        category="advanced",
        content=_h7020_native_diy_content(template_id, seed),
    )
    for template_id, _body_effect, label, seed in H7020_NATIVE_DIY_SEEDS
)

H705A_NATIVE_DIY_CONTRACTS: Final = tuple(
    NativeDiyTemplateContract(template_id, 89, 2, 5, 1, 8, "selected_movement_speed", 150, 250, 248, 508)
    for template_id in (17, 18)
)
H705A_NATIVE_DIY_TEMPLATES: Final = tuple(
    CatalogueTemplate(
        id=f"template:native-diy:{template_id}",
        label=f"Spin {index}",
        category="advanced",
        content=replace(
            decode_workshop_effect("H617A", base64.b64decode(H7020_NATIVE_DIY_SEEDS[0][3]))[0],
            native_diy=template_id,
        ),
    )
    for index, template_id in enumerate((17, 18), 1)
)
# H6102 presets 504/506 use 60. This is
# preset construction evidence, not permission to infer runtime physical geometry.
# The seven-colour defaults are used;
# raw carrier seeds do not themselves satisfy the editor's bounds.
_RGBIC_APP_PALETTE = ((255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (0, 255, 255), (139, 0, 255))


def _rgbic_native_palette(
    selector: int, index: int, original: tuple[tuple[int, int, int], ...]
) -> tuple[tuple[int, int, int], ...]:
    if selector == 501:
        return ((0, 0, 255),) if index == 0 else _RGBIC_APP_PALETTE[index - 1 :: 2]
    if selector == 504:
        return _RGBIC_APP_PALETTE[index::3]
    if selector == 506 and index < 2:
        return _RGBIC_APP_PALETTE[index::2]
    return original


def _rgbic_native_templates(preset_ic_count: int) -> tuple[CatalogueTemplate, ...]:
    return tuple(
        replace(
            template,
            content=replace(
                template.content,
                layers=tuple(
                    replace(
                        layer,
                        palette=_rgbic_native_palette(template.content.native_diy, index, layer.palette),
                        selection=replace(
                            layer.selection,
                            param_2=preset_ic_count // 5
                            if template.content.native_diy == 504
                            else preset_ic_count // 2,
                        )
                        if template.content.native_diy == 504 or template.content.native_diy == 506 and index >= 2
                        else layer.selection,
                    )
                    for index, layer in enumerate(template.content.layers)
                ),
            ),
        )
        for template in H617A_NATIVE_DIY_TEMPLATES
        if isinstance(template.content, LayeredEffect) and template.content.native_diy is not None
    )


H6102_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(60)
H6125_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(50)
H6117_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(50)
H617C_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(30)
H619A_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(20)
H617A_CATALOGUE_TEMPLATES: Final = (
    *_h617a_catalogue_templates("H617A", H617A_NATIVE_MUSIC_MODES),
    *H617A_NATIVE_DIY_TEMPLATES,
)
H617E_CATALOGUE_TEMPLATES: Final = _h617a_catalogue_templates("H617E", H617E_NATIVE_MUSIC_MODES)

H6179_CATALOGUE_TEMPLATES: Final = (
    *(_single_template("H6179", family) for family in H6179_DIY_FAMILIES),
    *(_music_template("H6179", mode) for mode in H6179_NATIVE_MUSIC_MODES),
)

H6199_CATALOGUE_TEMPLATES: Final = (
    *(_single_template("H6199", family) for family in H6199_PALETTE_DIY_FAMILIES),
    *(_music_template("H6199", mode) for mode in H6199_NATIVE_MUSIC_MODES),
    *(_video_template("H6199", mode) for mode in H6199_VIDEO_MODES),
)

H7020_CATALOGUE_TEMPLATES: Final = (
    *(_single_template("H7020", family, grammar="H617A") for family in H7020_DIY_FAMILIES),
    *(_music_template("H7020", mode) for mode in H7020_NATIVE_MUSIC_MODES),
    *H7020_NATIVE_DIY_TEMPLATES,
)

H7025_CATALOGUE_TEMPLATES: Final = (
    *(_single_template("H7025", family) for family in H7025_DIY_FAMILIES),
    *(_music_template("H7025", mode) for mode in _native_music_modes("H7025")),
)

WORKSHOP_PROTOCOL_FIXTURES: Final = (
    WorkshopTemplate(
        "movement-baseline",
        "Movement",
        "Ah1AAAACEgH/AACAFBSBsm0CAP8A/wAAFAHvEAG3ARoAAQAPEAH/AACAFBQBgBQBBv8AAACAAACAAAAAAAAAAAA=",
    ),
    WorkshopTemplate(
        "selected-area-movement-direction",
        "Selected-area movement",
        "Ah1AAAACEgH/AACAFBSDsm0CAP8A/wAAFgHvEAG3ARoAAQAPEAH/AACAFBQBgBQBBv8AAACAAACAAAAAAAAAAAA=",
    ),
    WorkshopTemplate(
        "overall-movement-direction",
        "Whole-layer movement",
        "Ah1AAAACEgH/AACAFBSDsm0CAP8A/wAAAAHvEgG3ABoAAQAPEAH/AACAFBQBgBQBBv8AAACAAACAAAAAAAAAAAA=",
    ),
    WorkshopTemplate(
        "two-colour-continuous-selection",
        "Continuous two-colour",
        "AR0AAQAPEAH/AACAFBQBgBQC/wAAAAD/AACAAACAAA==",
    ),
    WorkshopTemplate(
        "three-colour-palette",
        "Three-colour palette",
        "ASAAAQAPEAH/AACAFBQBgBQD/wAAAAD/AP8AAACAAACAAAAAAAAAAAAAAAAAAAAA",
    ),
    WorkshopTemplate(
        "brightness-scope",
        "Brightness range",
        "AR0AAQAPEAHGOQD/yDABfxQC/wAAAAD/AACAAACAAA==",
    ),
    WorkshopTemplate(
        "two-layer-priority",
        "Layer priority",
        "Ah1AAAACEgH/AACAFBSDsm0CAP8A/wAAAAHvEAG3AhoAAQAPEAH/AACAFBQBgBQBBv8AAACAAACAAAAAAAAAAAA=",
    ),
    WorkshopTemplate(
        "distribution-direction",
        "Distribution direction",
        "BRogAQACAAH/AACAFBSAgBQB/wAFAACAAACAABoiAQACAAH/AACAFBQBgBQBAP8EAACAAACAABokAQACAAH/AACAFBQBgBQB/wABAACAAACAABomAQACAAH/AACAFBQBgBQBAP8AAACAAACAABooAQABAAH/AACAFBQBgBQB/wAAAACAAACAAAAAAAAAAAAAAAAAAAAA",
    ),
    WorkshopTemplate(
        "matrix-customise",
        "Custom segments",
        "AR0AAwEAEAH/AACAFBQBgBQC/wAAAAD/AACAAACAAA==",
    ),
    WorkshopTemplate(
        "five-layer-applied-area",
        "Five applied areas",
        "BRogAQACAAH/AACAFBQBgBQB/wAFAACAAACAABoiAQACAAH/AACAFBQBgBQBAP8EAACAAACAABokAQACAAH/AACAFBQBgBQB/wABAACAAACAABomAQACAAH/AACAFBQBgBQBAP8AAACAAACAABooAQABAAH/AACAFBQBgBQB/wAAAACAAACAAAAAAAAAAAAAAAAAAAAA",
    ),
)

_H1771_FIRST = H1771DiyBody.FirstEffect
_H1771_SECOND = H1771DiyBody.SecondEffect
_H1771_DISABLED = NativeDiyLayer(0, 0, (), enabled=False, opaque=b"\x00")
_H1771_PALETTE = (DEFAULT_PALETTE[0], DEFAULT_PALETTE[3])
_H1771_SECTIONS = (
    (
        ("Temperature", NativeDiyLayer(_H1771_FIRST.temperature, 50, (), parameter=100, angle=1700)),
        ("Fade", NativeDiyLayer(_H1771_FIRST.palette_4, 50, _H1771_PALETTE)),
        ("Breathe", NativeDiyLayer(_H1771_FIRST.palette_2, 50, _H1771_PALETTE)),
        ("Blink", NativeDiyLayer(_H1771_FIRST.palette_3, 50, _H1771_PALETTE)),
    ),
    (
        ("Temperature", NativeDiyLayer(_H1771_SECOND.temperature, 50, (), parameter=100, angle=1700)),
        ("Fade 1", NativeDiyLayer(_H1771_SECOND.common_1, 50, _H1771_PALETTE, parameter=1)),
        ("Fade 2", NativeDiyLayer(_H1771_SECOND.common_1, 50, _H1771_PALETTE, parameter=2)),
        ("Jump 1", NativeDiyLayer(_H1771_SECOND.common_2, 50, _H1771_PALETTE, parameter=1)),
        ("Jump 2", NativeDiyLayer(_H1771_SECOND.common_2, 50, _H1771_PALETTE, parameter=2)),
        ("Breathe 1", NativeDiyLayer(_H1771_SECOND.breathe, 50, _H1771_PALETTE, parameter=255)),
        ("Breathe 2", NativeDiyLayer(_H1771_SECOND.breathe, 50, _H1771_PALETTE, parameter=3, flag=1)),
        ("Chase", NativeDiyLayer(_H1771_SECOND.common_3, 50, _H1771_PALETTE, parameter=1)),
        ("Flow", NativeDiyLayer(_H1771_SECOND.common_5, 50, _H1771_PALETTE, parameter=1)),
        ("Stream", NativeDiyLayer(_H1771_SECOND.common_4, 50, _H1771_PALETTE, parameter=2)),
        ("Swing", NativeDiyLayer(_H1771_SECOND.palette_6, 50, _H1771_PALETTE)),
        ("Streamer", NativeDiyLayer(_H1771_SECOND.streamer, 50, _H1771_PALETTE, parameter=1, flag=1)),
        ("Background", NativeDiyLayer(_H1771_SECOND.background, 50, _H1771_PALETTE, secondary_palette=((0, 0, 0),))),
        ("Stack 1", NativeDiyLayer(_H1771_SECOND.stack, 50, _H1771_PALETTE, parameter=2)),
        ("Stack 2", NativeDiyLayer(_H1771_SECOND.stack, 50, _H1771_PALETTE, parameter=2, flag=1)),
        ("Refresh", NativeDiyLayer(_H1771_SECOND.palette_14, 50, _H1771_PALETTE)),
    ),
)


def _h1771_rate_min(index: int, kind: int) -> int:
    if index == 0:
        return 0 if kind == _H1771_FIRST.temperature else 1
    return (
        0
        if kind in (_H1771_SECOND.temperature, _H1771_SECOND.common_1, _H1771_SECOND.common_2, _H1771_SECOND.breathe)
        else 1
    )


def _h1771_templates() -> tuple[CatalogueTemplate, ...]:
    return tuple(
        CatalogueTemplate(
            id=f"template:h1771:{index}:{number}",
            label=f"Section {index + 1} {label}",
            category="single-layer",
            content=NativeEffect(
                model="H1771",
                family=int(H1771DiyBody.CatalogueFamily.native_scene),
                layers=(
                    (layer, _H1771_DISABLED)
                    if index == 0
                    else (
                        NativeDiyLayer(
                            _H1771_FIRST.temperature, layer.speed, (), parameter=layer.parameter, angle=layer.angle
                        )
                        if layer.kind == _H1771_SECOND.temperature
                        else NativeDiyLayer(_H1771_FIRST.palette_4, layer.speed, layer.palette),
                        layer,
                    )
                ),
            ),
            rate_min=_h1771_rate_min(index, layer.kind),
        )
        for index, choices in enumerate(_H1771_SECTIONS)
        for number, (label, layer) in enumerate(choices)
    )


def _native_zone_layer(family: DiyEffectFamily, variant: int | None = None) -> NativeDiyLayer:
    return NativeDiyLayer(
        kind=family.family,
        parameter=family.variations[0].variant if variant is None else variant,
        speed=50,
        palette=DEFAULT_PALETTE[: family.palette_max or 8],
        secondary_palette=DEFAULT_PALETTE[: family.secondary_palette_max] if family.secondary_palette_max else (),
    )


def _h607c_templates() -> tuple[CatalogueTemplate, ...]:
    return (
        CatalogueTemplate(
            id="template:paint",
            label="Paint",
            category="single-layer",
            content=PaintedEffect(
                effect=H607cPaintBody.Direction.upward.name,
                speed=0,
                brightness=100,
                segments=(None,) * MODEL_PROFILES["H607C"].native_zones[0][2],
                addressing="physical_ic",
                model="H607C",
            ),
        ),
        *(
            CatalogueTemplate(
                id=f"template:native:{family.family}:{variation.variant}",
                label=f"{family.label} {index + 1}" if len(family.variations) > 1 else family.label,
                category="single-layer",
                content=NativeEffect(
                    model="H607C",
                    family=family.family,
                    layers=(_native_zone_layer(family, variation.variant),),
                    preset_id=family.family,
                ),
            )
            for family in H607C_DIY_FAMILIES
            for index, variation in enumerate(family.variations)
        ),
        CatalogueTemplate(
            id="template:native:paired",
            label="Pole and base",
            category="multi-layer",
            content=NativeEffect(
                model="H607C",
                family=int(H607cDiyBody.Family.paired),
                layers=(_native_zone_layer(H607C_DIY_FAMILIES[0]), _native_zone_layer(H607C_DIY_FAMILIES[1])),
            ),
        ),
        *(_music_template("H607C", mode) for mode in H607C_NATIVE_MUSIC_MODES),
    )


def _ceiling_catalogue(model: str) -> ModelEffectCatalogue:
    native = model == "H60A6"
    return ModelEffectCatalogue(
        sku=model,
        painted_effects=(),
        effects=() if native else H60A1_DIY_FAMILIES,
        music_modes=(),
        video_modes=(),
        workshop_templates=(),
        templates=tuple(
            CatalogueTemplate(
                id=f"template:native:{preset}",
                label="Paint" if preset == 15 else f"Native preset {preset}",
                category="advanced" if preset in (11, 12, 15) else "single-layer",
                content=native_diy_preset(preset, DEFAULT_PALETTE),
            )
            for preset in range(1, 16)
        )
        if native
        else tuple(_single_template(model, family, grammar="H617A") for family in H60A1_DIY_FAMILIES),
        advanced_create=False,
        temporary_diy_selector=254,
        native_actions=tuple(
            NativeModeOption(str(int(action)), f"Native action {int(action)}") for action in H60a6PaintBody.ActionCode
        )
        if native
        else (),
    )


def _h60b0_templates() -> tuple[CatalogueTemplate, ...]:
    palette = (DEFAULT_PALETTE[0], DEFAULT_PALETTE[4])
    disabled = NativeDiyLayer(1, 50, (), enabled=False, parameter=50, direction=1)
    off = NativeDiyLayer(1, 0, ())
    names = ("Fade", "Breathe", "Blink", "Stream", "Colour wall", "Flow", "Alternate", "Shimmer", "Cover", "Variety")
    templates: list[CatalogueTemplate] = []
    for kind, label in enumerate(names, 1):
        layer = NativeDiyLayer(
            kind,
            50,
            palette,
            parameter=1 if kind == 9 else 0,
            secondary_palette=((0, 0, 0),) if kind == 8 else (),
        )
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:1:single:{kind}",
                label=label,
                category="single-layer",
                content=NativeEffect(model="H60B0", revision=1, family=kind, layers=(layer,)),
                rate_min=1,
            )
        )
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:1:1:{kind}",
                label=f"Side {label}",
                category="advanced",
                content=NativeEffect(
                    model="H60B0",
                    revision=1,
                    family=13,
                    layers=(
                        NativeDiyLayer(0, 0, (), enabled=False),
                        replace(layer, parameter=0 if kind == 9 else layer.parameter),
                    ),
                ),
                rate_min=1,
            )
        )
    for kind, label in ((1, "Fade"), (2, "Breathe"), (4, "Stream"), (11, "Blink"), (12, "Jump")):
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:1:0:{kind}",
                label=f"Ripple {label}",
                category="advanced",
                content=NativeEffect(
                    model="H60B0",
                    revision=1,
                    family=13,
                    layers=(
                        NativeDiyLayer(kind, 50, palette, direction=1, flag=50),
                        NativeDiyLayer(0, 0, (), enabled=False),
                    ),
                ),
                rate_min=1,
            )
        )
    side_names = (
        "Fade",
        "Breathe",
        "Stream",
        "Blink",
        "Colour wall",
        "Flow",
        "Alternate",
        "Shimmer",
        "Cover",
        "Variety",
        "Spread",
        "Meteor",
    )
    for kind, label in enumerate(side_names, 2):
        layer = NativeDiyLayer(
            kind,
            50,
            palette,
            points=(0, 100) if kind in (3, 5) else (),
            direction=3 if kind == 12 else 1 if kind in (7, 10) else 0,
            secondary_palette=((0, 0, 0),) if kind == 9 else (),
        )
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:3:1:{kind}",
                label=f"Side {label}",
                category="multi-layer",
                content=NativeEffect(model="H60B0", revision=3, family=922, layers=(disabled, layer, off)),
                rate_min=1,
            )
        )
    for kind, label in ((2, "Fade"), (3, "Breathe"), (4, "Stream"), (5, "Blink"), (6, "Jump")):
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:3:0:{kind}",
                label=f"Ripple {label}",
                category="advanced",
                content=NativeEffect(
                    model="H60B0",
                    revision=3,
                    family=923,
                    layers=(
                        NativeDiyLayer(
                            kind, 50, palette, parameter=50, direction=1, points=(0, 100) if kind in (3, 5) else ()
                        ),
                        off,
                        off,
                    ),
                ),
                rate_min=1,
            )
        )
    for kind, label in ((2, "Fade"), (3, "Breathe")):
        templates.append(
            CatalogueTemplate(
                id=f"template:h60b0:3:2:{kind}",
                label=f"Bottom {label}",
                category="multi-layer",
                content=NativeEffect(
                    model="H60B0",
                    revision=3,
                    family=922,
                    layers=(
                        disabled,
                        off,
                        NativeDiyLayer(
                            kind, 50, ((255, 255, 255),), points=(0, 100) if kind == 3 else (1,), temperatures=(6500,)
                        ),
                    ),
                ),
                rate_min=1,
            )
        )
    templates.append(
        CatalogueTemplate(
            id="template:h60b0:3:0:7",
            label="Top temperature",
            category="advanced",
            content=NativeEffect(
                model="H60B0",
                revision=3,
                family=923,
                layers=(NativeDiyLayer(7, 0, (), parameter=50, direction=1, flag=100, angle=4000), off, off),
            ),
        )
    )
    from .h60b0_effects import decode_combined_scene
    from .layered_scene import CatalogueRef
    from .scenes import SCENE_ENTRIES

    seed = next(scene for scene in SCENE_ENTRIES["H60B0"] if scene.scene_type == 6 and scene.param)
    templates.append(
        CatalogueTemplate(
            id="template:h60b0:combined",
            label="Side and ripple layers",
            category="multi-layer",
            content=NativeEffect(
                model="H60B0",
                family=81,
                layers=(),
                combined=decode_combined_scene(
                    CatalogueRef("H60B0", 0, 510), base64.b64decode(seed.param, validate=True)
                ),
            ),
        )
    )
    return tuple(templates)
