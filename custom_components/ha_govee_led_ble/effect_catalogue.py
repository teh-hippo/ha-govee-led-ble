"""Versioned Effect Studio catalogue contracts."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from typing import Final

from .const import MODEL_PROFILES, MUSIC_MODE_SLUGS, ModelProfile, get_profile, supported_effect_categories
from .effect_contracts import (
    CapabilityState,
    CapabilityWorkflow,
    frontend_release_capabilities,
    studio_apply_capability_state,
    workflow_capability_state,
)
from .effect_domain import (
    MAX_MULTI_EFFECTS,
    EffectContent,
    EffectValidationError,
    JsonValue,
    LayeredEffect,
    MultiEffect,
    MusicProfile,
    PaintedEffect,
    PaletteDiyEffect,
    RelativeBrightness,
    SingleEffect,
    VideoProfile,
    WorkshopEffect,
    effect_content_to_dict,
)
from .generated_protocol.diy_type03 import DiyType03  # type: ignore[attr-defined]
from .generated_protocol_adapter import music_default_palette
from .layered_scene_decoder import decode_workshop_effect
from .music_commands import music_default_available
from .music_semantics import music_parameters_available, music_params_for_mode, music_variant

EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION: Final = 10
LEGACY_CATALOGUE_SKU: Final = "H617A"

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


@dataclass(frozen=True, slots=True)
class DiyEffectTemplate:
    id: str
    label: str
    family: int
    variant: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "family": self.family,
            "variant": self.variant,
        }


@dataclass(frozen=True, slots=True)
class DiyEffectVariation:
    id: str
    label: str
    variant: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "variant": self.variant,
        }


@dataclass(frozen=True, slots=True)
class DiyEffectFamily:
    id: str
    label: str
    family: int
    variations: tuple[DiyEffectVariation, ...]
    supports_multi: bool
    rate: str = "speed"
    source_reference: str = "GoveeHome V7.5.30 dreamcolorlightv1.adjust.Diy"
    category: str = "single_layer"
    rate_min: int = 0
    rate_max: int = 100
    palette_max: int | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "family": self.family,
            "variations": [variation.to_dict() for variation in self.variations],
            "supports_multi": self.supports_multi,
            "rate": self.rate,
            "category": self.category,
            "rate_min": self.rate_min,
            "rate_max": self.rate_max,
            **({"palette_max": self.palette_max} if self.palette_max is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class NativeModeOption:
    id: str
    label: str

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class WorkshopTemplate:
    id: str
    label: str
    raw_param_b64: str

    def content(self, model: str) -> WorkshopEffect:
        raw_param = base64.b64decode(self.raw_param_b64, validate=True)
        effect, trailing_padding = decode_workshop_effect(model, raw_param)
        return WorkshopEffect(
            model=model,
            template=self.id,
            effect=effect,
            raw_param=raw_param,
            trailing_padding=trailing_padding,
        )

    def to_dict(self, model: str) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "content": effect_content_to_dict(self.content(model)),
        }


@dataclass(frozen=True, slots=True)
class CatalogueTemplate:
    id: str
    label: str
    category: str
    content: EffectContent

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "content": effect_content_to_dict(self.content),
        }


@dataclass(frozen=True, slots=True)
class CatalogueSupport:
    multi: CapabilityState
    advanced: CapabilityState
    workshop: CapabilityState

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "multi": self.multi.value,
            "advanced": self.advanced.value,
            "workshop": self.workshop.value,
        }


@dataclass(frozen=True, slots=True)
class ApplySupport:
    painted: CapabilityState
    single: CapabilityState
    multi: CapabilityState
    palette_diy: CapabilityState
    workshop: CapabilityState

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "painted": self.painted.value,
            "single": self.single.value,
            "multi": self.multi.value,
            "palette_diy": self.palette_diy.value,
            "workshop": self.workshop.value,
        }


@dataclass(frozen=True, slots=True)
class ModelEffectCatalogue:
    sku: str
    painted_effects: tuple[dict[str, str], ...]
    effects: tuple[DiyEffectFamily, ...]
    music_modes: tuple[NativeModeOption, ...]
    video_modes: tuple[NativeModeOption, ...]
    templates: tuple[CatalogueTemplate, ...]
    workshop_templates: tuple[WorkshopTemplate, ...]
    supports: CatalogueSupport
    apply: ApplySupport
    palette_min: int = 1
    palette_max: int = 8
    multi_max: int = MAX_MULTI_EFFECTS
    speed_min: int = 0
    speed_max: int = 100
    brightness_min: int = 0
    brightness_max: int = 100
    painted_addressing: str = "segments"
    painted_background: tuple[int, int, int] = (0, 0, 0)

    def to_dict(self, *, profile: ModelProfile | None = None) -> dict[str, JsonValue]:
        profile = MODEL_PROFILES[self.sku] if profile is None else profile
        result: dict[str, JsonValue] = {
            "sku": self.sku,
            "painted_effects": [dict(effect) for effect in self.painted_effects],
            **(
                {"painted_addressing": self.painted_addressing, "painted_background": list(self.painted_background)}
                if self.painted_addressing != "segments"
                else {}
            ),
            "effects": [effect.to_dict() for effect in self.effects],
            "music_modes": [mode.to_dict() for mode in self.music_modes],
            "music_settings": {
                mode.id: {
                    "available": music_default_available(self.sku, mode.id, profile=profile),
                    "style": bool(
                        (variant := music_variant(profile, MUSIC_MODE_SLUGS[mode.id])) and variant.supports_style
                    ),
                    "calm_default": variant.calm_default if variant else False,
                    "colour": bool(profile.supports_music_color and variant and variant.supports_fixed_colour),
                    "evidence": variant.evidence if variant else None,
                    "palette_size": variant.template[1] if variant and variant.template else 0,
                    **(
                        {
                            "palette": {
                                "min": variant.palette_bounds[0],
                                "max": variant.palette_bounds[1],
                                "default": [list(rgb) for rgb in music_default_palette(variant)],
                            }
                        }
                        if variant and variant.palette_bounds and music_parameters_available(profile, variant)
                        else {}
                    ),
                    "parameters": {
                        spec.profile_key: {
                            "kind": spec.kind,
                            "default": spec.default,
                            "min": spec.min_value,
                            "max": spec.max_value,
                            "options": list(spec.options),
                        }
                        for spec in music_params_for_mode(MUSIC_MODE_SLUGS[mode.id], profile)
                    },
                }
                for mode in self.music_modes
            },
            "video_modes": [mode.to_dict() for mode in self.video_modes],
            "video_settings": list(_video_profile_settings(profile)),
            "video_controls": {
                "saturation_min": profile.video_saturation_min,
                "white_balance": {
                    "representation": profile.video_white_balance_representation,
                    "minimum": profile.video_white_balance_min,
                    "maximum": profile.video_white_balance_max,
                    "default": profile.video_white_balance_default,
                },
                "brightness_zones": list(profile.video_brightness_zones),
            },
            "templates": [template.to_dict() for template in self.templates],
            "workshop_templates": [template.to_dict(self.sku) for template in self.workshop_templates],
            "workflows": frontend_release_capabilities(self.sku),
            "supports": self.supports.to_dict(),
            "limits": {
                "palette_min": self.palette_min,
                "palette_max": self.palette_max,
                "multi_max": self.multi_max,
                "speed_min": self.speed_min,
                "speed_max": self.speed_max,
                "brightness_min": self.brightness_min,
                "brightness_max": self.brightness_max,
                "music_sensitivity_min": profile.music_sensitivity_min,
                "music_sensitivity_max": profile.music_sensitivity_max,
            },
            "apply": self.apply.to_dict(),
        }
        if profile.command_operations is not None and not supported_effect_categories(self.sku, profile=profile):
            for key in (
                "painted_effects",
                "effects",
                "music_modes",
                "video_modes",
                "templates",
                "workshop_templates",
                "workflows",
            ):
                result[key] = []
            result["music_settings"] = {}
            result["supports"] = {key: CapabilityState.UNSUPPORTED.value for key in self.supports.to_dict()}
            result["apply"] = {key: CapabilityState.UNSUPPORTED.value for key in self.apply.to_dict()}
        return result


# GoveeHome V7.5.30 exposes these basic Type04 families through
# dreamcolorlightv1.adjust.Diy.e(), with the same base roster retained by later
# revisions.  The family and variation bytes use the structure defined by
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

# Android 7.6.01 pact_h6099/detail/diy/H6099DiyConfig, goods 191.
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
        source_reference="Android 7.6.01 H6099DiyConfig.getBasicEffectList/getMixEffectList",
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


def _mode_label(slug: str) -> str:
    return slug.replace("_", " ").title()


def _native_music_modes(model: str) -> tuple[NativeModeOption, ...]:
    supported = frozenset(MODEL_PROFILES[model].music_modes)
    return tuple(
        NativeModeOption(
            slug,
            _mode_label(slug),
        )
        for slug in MUSIC_MODE_SLUGS
        if slug in supported
    )


H617A_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617A")
H617A_WORKSHOP_APPLY_CODE: Final = 401
H617A_WORKSHOP_SCENE_TYPE: Final = 2
H6199_DIY_SOURCE_REFERENCE: Final = "tools/ble/kaitai/h6199_effect_upload.ksy"
H6199_PALETTE_DIY_APPLY_CODE: Final = 401
H6199_PALETTE_DIY_APPLY_MUSIC_CODE: Final = 2
H6199_WORKSHOP_APPLY_CODE: Final = 402
H6199_WORKSHOP_APPLY_MUSIC_CODE: Final = 0

H6199_DIY_EFFECTS: Final = (
    DiyEffectTemplate(
        "fade",
        "Fade",
        0,
        0,
    ),
    DiyEffectTemplate(
        "jumping",
        "Jumping",
        1,
        0,
    ),
    DiyEffectTemplate(
        "twinkle",
        "Twinkle",
        2,
        0,
    ),
    DiyEffectTemplate(
        "marquee",
        "Marquee",
        3,
        3,
    ),
    DiyEffectTemplate(
        "music",
        "Music",
        4,
        8,
    ),
    DiyEffectTemplate(
        "chasing",
        "Chasing",
        8,
        9,
    ),
    DiyEffectTemplate(
        "chasing_counterclockwise",
        "Chasing Counterclockwise",
        8,
        10,
    ),
    DiyEffectTemplate(
        "rainbow",
        "Rainbow",
        9,
        9,
    ),
    DiyEffectTemplate(
        "crossing",
        "Crossing",
        10,
        0,
    ),
)

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


def _video_profile_settings(profile: ModelProfile) -> tuple[str, ...]:
    return tuple(
        name
        for name, supported in (
            ("capture_region", profile.supports_video_capture_region),
            ("saturation", profile.supports_video_saturation),
            ("sound_effects", profile.supports_video_sound_effects),
            ("white_balance", profile.supports_white_balance),
            ("relative_brightness", profile.supports_relative_brightness),
            ("blank_screen", profile.supports_blank_screen),
            ("black_border", profile.supports_black_border),
        )
        if supported
    )


H6199_VIDEO_MODES: Final = _native_video_modes("H6199")


def _single_template(model: str, family: DiyEffectFamily) -> CatalogueTemplate:
    variation = family.variations[0]
    content: EffectContent
    grammar = get_profile(model).effect_grammar
    if grammar in {"H617A", "H6099"}:
        content = SingleEffect(
            family=family.family,
            variant=variation.variant,
            speed=50,
            palette=((255, 0, 0), (0, 255, 0), (0, 0, 255)) if family.palette_max == 3 else DEFAULT_PALETTE,
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
    variant = music_variant(profile, MUSIC_MODE_SLUGS[mode.id])
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
                if profile.supports_relative_brightness
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


# Android 7.6.01 ParamsV2 seeds, in selector order (DiyM 1087..1117).
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
H617A_CATALOGUE_TEMPLATES: Final = (
    *_h617a_catalogue_templates("H617A", H617A_NATIVE_MUSIC_MODES),
    *H617A_NATIVE_DIY_TEMPLATES,
)
H617E_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617E")
H617E_CATALOGUE_TEMPLATES: Final = _h617a_catalogue_templates("H617E", H617E_NATIVE_MUSIC_MODES)

H6199_CATALOGUE_TEMPLATES: Final = (
    *(_single_template("H6199", family) for family in H6199_PALETTE_DIY_FAMILIES),
    *(_music_template("H6199", mode) for mode in H6199_NATIVE_MUSIC_MODES),
    *(_video_template("H6199", mode) for mode in H6199_VIDEO_MODES),
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

MODEL_EFFECT_CATALOGUES: Final = {
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6099", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6099", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6099", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6099", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6099", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6099", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6099", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6099", CapabilityWorkflow.WORKSHOP),
        ),
    ),
    "H617A": ModelEffectCatalogue(
        sku="H617A",
        painted_effects=H617A_PAINTED_EFFECTS,
        effects=H617A_TYPE04_FAMILIES,
        music_modes=H617A_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H617A_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        supports=CatalogueSupport(
            multi=workflow_capability_state("H617A", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H617A", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H617A", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H617A", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H617A", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H617A", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H617A", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H617A", CapabilityWorkflow.WORKSHOP),
        ),
    ),
    "H617E": ModelEffectCatalogue(
        sku="H617E",
        painted_effects=H617A_PAINTED_EFFECTS,
        effects=tuple(replace(family, palette_max=None) for family in H617A_TYPE04_FAMILIES),
        music_modes=H617E_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H617E_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        supports=CatalogueSupport(
            multi=workflow_capability_state("H617E", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H617E", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H617E", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H617E", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H617E", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H617E", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H617E", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H617E", CapabilityWorkflow.WORKSHOP),
        ),
    ),
    "H6199": ModelEffectCatalogue(
        sku="H6199",
        painted_effects=(),
        effects=H6199_PALETTE_DIY_FAMILIES,
        music_modes=H6199_NATIVE_MUSIC_MODES,
        video_modes=H6199_VIDEO_MODES,
        templates=H6199_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6199", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6199", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6199", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6199", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6199", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6199", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6199", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6199", CapabilityWorkflow.WORKSHOP),
        ),
    ),
}


def validate_effect_eligibility(
    content: PaintedEffect | SingleEffect | MultiEffect | PaletteDiyEffect,
    model: str,
    *,
    profile: ModelProfile | None = None,
) -> None:
    """Authorize content against the target catalogue, not its shared wire grammar."""
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    if catalogue is None:
        raise ValueError(f"{model} has no custom-effect catalogue")
    if isinstance(content, PaintedEffect):
        if content.effect not in {effect["id"] for effect in catalogue.painted_effects}:
            raise ValueError(f"{model} painted effect {content.effect!r} is not supported")
        profile = get_profile(model) if profile is None else profile
        if profile.effect_grammar != get_profile(model).effect_grammar:
            raise ValueError(f"{model} effective profile has a different effect grammar")
        physical = profile.effect_grammar == "H6099"
        if content.addressing != ("physical_ic" if physical else "segments"):
            raise ValueError(f"{model} painted addressing does not match")
        count = profile.physical_ic_count if physical else profile.segment_count
        if count is None:
            raise ValueError(f"{model} graffiti requires a known physical IC count")
        if len(content.segments) != count:
            raise ValueError(f"{model} painted segment count does not match")
        if not catalogue.brightness_min <= content.brightness <= catalogue.brightness_max:
            raise ValueError(f"{model} painted brightness is outside catalogue limits")
    else:
        if not catalogue.palette_min <= len(content.palette) <= catalogue.palette_max:
            raise ValueError(f"{model} palette is outside catalogue limits")
        multi = isinstance(content, MultiEffect)
        if isinstance(content, MultiEffect) and len(content.effects) > catalogue.multi_max:
            raise ValueError(f"{model} Multi count is outside catalogue limits")
        pairs = content.effects if isinstance(content, MultiEffect) else (content,)
        for pair in pairs:
            family = next((family for family in catalogue.effects if family.family == pair.family), None)
            if family is None or pair.variant not in {variation.variant for variation in family.variations}:
                raise ValueError(f"{model} family {pair.family} variation {pair.variant} is not supported")
            if multi and not family.supports_multi:
                raise ValueError(f"{model} family {pair.family} does not support Multi")
            if family.palette_max is not None and len(content.palette) > family.palette_max:
                raise ValueError(f"{model} family {pair.family} palette is outside catalogue limits")
            if not family.rate_min <= content.speed <= family.rate_max:
                raise ValueError(f"{model} family {pair.family} {family.rate} is outside catalogue limits")
    if (
        isinstance(content, PaintedEffect | MultiEffect)
        and not catalogue.speed_min <= content.speed <= catalogue.speed_max
    ):
        raise ValueError(f"{model} speed is outside catalogue limits")


def validate_native_diy(content: LayeredEffect, model: str, profile: ModelProfile) -> None:
    """Only geometry-dependent edits need IC metadata; APK seeds remain presets."""
    if model != "H617A" or profile.effect_grammar != "H617A":
        raise ValueError("native DIY templates 501..507 target H617A only")
    template = next(
        (
            t
            for t in H617A_NATIVE_DIY_TEMPLATES
            if isinstance(t.content, LayeredEffect) and t.content.native_diy == content.native_diy
        ),
        None,
    )
    if template is None:
        raise ValueError("unknown native DIY template")
    seed = template.content
    assert isinstance(seed, LayeredEffect)
    if len(content.layers) != len(seed.layers):
        raise ValueError("native DIY must retain its template layer count")
    for index, (layer, original) in enumerate(zip(content.layers, seed.layers, strict=True)):
        if not 1 <= len(layer.palette) <= 8:
            raise ValueError("native DIY layer palette must contain 1 to 8 colours")
        dependent = (
            content.native_diy == 502
            and layer.selection != original.selection
            or content.native_diy == 504
            and layer.selection != original.selection
            or content.native_diy == 506
            and index >= 2
            and (
                layer.selection != original.selection
                or layer.area != original.area
                or layer.selected_movement.direction != original.selected_movement.direction
            )
            or content.native_diy == 503
            and len(layer.palette) != len(original.palette)
        )
        if dependent and profile.physical_ic_count is None:
            raise ValueError("this native DIY geometry edit requires a known physical IC count")
        if profile.physical_ic_count is not None:
            count = profile.physical_ic_count
            if (
                content.native_diy == 502
                and layer.selection != original.selection
                and not (
                    layer.selection.type == 2
                    and 1 <= layer.selection.random_ic_min <= layer.selection.random_ic_max <= min(25, count * 4 // 5)
                )
            ):
                raise ValueError("Sky star size is outside APK physical-IC bounds")
            if (
                content.native_diy == 503
                and len(layer.palette) != len(original.palette)
                and len(layer.palette) > min(max(1, count * 2 // 10), 8)
            ):
                raise ValueError("Meteor palette is outside APK physical-IC bounds")
            if (
                content.native_diy == 504
                and layer.selection != original.selection
                and (layer.selection.type != 1 or layer.selection.quantity != count // 5)
            ):
                raise ValueError("Meteor Shower selection must use physical IC count / 5")
            if (
                content.native_diy == 506
                and index >= 2
                and layer.selection != original.selection
                and (layer.selection.type != 1 or layer.selection.quantity not in (1, count, count // 2))
            ):
                raise ValueError("Bloom selection must use one, all, or half the physical IC count")


def resolve_catalogue_template(
    model: str,
    template_id: str,
    *,
    profile: ModelProfile | None = None,
) -> CatalogueTemplate:
    if (
        profile is not None
        and profile.command_operations is not None
        and not supported_effect_categories(model, profile=profile)
    ):
        raise ValueError("Device profile supports no effect templates")
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    if catalogue is None:
        raise ValueError(f"{model} has no custom-effect catalogue")
    for template in catalogue.templates:
        if template.id == template_id:
            if isinstance(template.content, PaintedEffect) and template.content.addressing == "physical_ic":
                count = (get_profile(model) if profile is None else profile).physical_ic_count
                if count is None:
                    raise ValueError(f"{model} graffiti requires a known physical IC count")
                return replace(template, content=replace(template.content, segments=(None,) * count))
            return template
    raise ValueError(f"{model} template {template_id!r} was not found")


def validate_catalogue_template_identity(
    model: str,
    template_id: str,
    content: EffectContent,
    *,
    profile: ModelProfile | None = None,
) -> CatalogueTemplate:
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    template = next((entry for entry in catalogue.templates if entry.id == template_id), None) if catalogue else None
    if template is None:
        raise EffectValidationError(f"{model} template {template_id!r} was not found")
    canonical = template.content
    valid = (
        isinstance(canonical, PaintedEffect)
        and isinstance(content, PaintedEffect)
        and canonical.addressing == content.addressing
        or isinstance(canonical, SingleEffect)
        and isinstance(content, SingleEffect)
        and (content.family, content.variant) == (canonical.family, canonical.variant)
        or isinstance(canonical, PaletteDiyEffect)
        and isinstance(content, PaletteDiyEffect)
        and (content.model, content.family, content.variant) == (canonical.model, canonical.family, canonical.variant)
        or isinstance(canonical, MusicProfile)
        and isinstance(content, MusicProfile)
        and (content.model, content.mode) == (canonical.model, canonical.mode)
        or isinstance(canonical, VideoProfile)
        and isinstance(content, VideoProfile)
        and (content.model, content.mode) == (canonical.model, canonical.mode)
        or isinstance(canonical, LayeredEffect)
        and isinstance(content, LayeredEffect)
        and content.native_diy == canonical.native_diy
    )
    if not valid:
        raise EffectValidationError(
            f"content does not match the structural identity of {model} template {template_id!r}"
        )
    return resolve_catalogue_template(model, template_id, profile=profile) if profile is not None else template


def custom_effect_catalogue_payload() -> dict[str, JsonValue]:
    legacy = MODEL_EFFECT_CATALOGUES[LEGACY_CATALOGUE_SKU].to_dict()
    return {
        "schema_version": EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION,
        **legacy,
        "models": {sku: catalogue.to_dict() for sku, catalogue in MODEL_EFFECT_CATALOGUES.items()},
    }
