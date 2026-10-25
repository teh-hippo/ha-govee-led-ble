"""Versioned Effect Studio catalogue contracts."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from typing import Final

from .const import MODEL_PROFILES, ModelProfile, get_profile, supported_effect_categories
from .effect_contracts import (
    CapabilityState,
    CapabilityWorkflow,
    frontend_release_capabilities,
    profile_supports_workflow,
    studio_apply_capability_state,
    workflow_capability_state,
)
from .effect_domain import (
    MAX_MULTI_EFFECTS,
    EffectContent,
    EffectValidationError,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    JsonValue,
    LayeredEffect,
    MultiEffect,
    MusicProfile,
    NativeEffect,
    PaintedEffect,
    PaletteDiyEffect,
    RelativeBrightness,
    SingleEffect,
    VideoProfile,
    WorkshopEffect,
    effect_content_to_dict,
)
from .generated_protocol.diy_type03 import DiyType03  # type: ignore[attr-defined]
from .h60a6_effects import native_diy_preset
from .layered_scene_decoder import decode_workshop_effect
from .music_commands import music_default_available
from .music_protocol import music_code_for, music_codebook
from .music_semantics import music_parameters_available, music_params_for_mode, music_variant
from .protocol_core import H60a6PaintBody
from .protocol_music_params import music_default_palette

EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION: Final = 11
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
    multi_rate_min: int | None = None

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
            **({"multi_rate_min": self.multi_rate_min} if self.multi_rate_min is not None else {}),
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
class NativeDiyTemplateContract:
    template_id: int
    body_effect: int
    upload_subtype: int
    layer_count: int
    palette_min: int
    palette_max: int
    rate_field: str
    rate_min: int
    rate_max: int
    rate_default: int

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "template_id": self.template_id,
            "body_effect": self.body_effect,
            "upload_subtype": self.upload_subtype,
            "layer_count": self.layer_count,
            "palette_min": self.palette_min,
            "palette_max": self.palette_max,
            "rate_field": self.rate_field,
            "rate_min": self.rate_min,
            "rate_max": self.rate_max,
            "rate_default": self.rate_default,
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
    # Exact-model APK authoring bounds; wire grammar alone does not qualify them.
    native_diy_palette_groups: tuple[tuple[int, tuple[int, ...], int, int], ...] = ()
    native_diy_templates: tuple[NativeDiyTemplateContract, ...] = ()
    diy_slot_policy: str = "fixed"
    advanced_create: bool = True
    temporary_diy_selector: int | None = None
    native_actions: tuple[NativeModeOption, ...] = ()

    def to_dict(self, *, profile: ModelProfile | None = None) -> dict[str, JsonValue]:
        device_profile = profile
        profile = MODEL_PROFILES[self.sku] if profile is None else profile
        result: dict[str, JsonValue] = {
            "sku": self.sku,
            **({"native_actions": [action.to_dict() for action in self.native_actions]} if self.native_actions else {}),
            "painted_effects": [
                dict(effect)
                for effect in self.painted_effects
                if device_profile is None or profile_supports_workflow(profile, CapabilityWorkflow.PAINTED)
            ],
            **(
                {"painted_addressing": self.painted_addressing, "painted_background": list(self.painted_background)}
                if self.painted_addressing != "segments"
                else {}
            ),
            "effects": [
                effect.to_dict()
                for effect in self.effects
                if device_profile is None or profile_supports_workflow(profile, CapabilityWorkflow.SINGLE)
            ],
            "music_modes": [mode.to_dict() for mode in self.music_modes if mode.id in profile.music_modes],
            "music_settings": {
                mode.id: {
                    "available": music_default_available(self.sku, mode.id, profile=profile),
                    "style": bool(
                        (variant := music_variant(profile, music_code_for(self.sku, mode.id, profile=profile)))
                        and variant.supports_style
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
                        for spec in music_params_for_mode(
                            music_code_for(self.sku, mode.id, profile=profile),
                            profile,
                        )
                    },
                }
                for mode in self.music_modes
                if mode.id in profile.music_modes
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
            "templates": [
                _template_for_profile(template, device_profile).to_dict()
                for template in self.templates
                if device_profile is None or _template_available(template, profile)
            ],
            "workshop_templates": [
                template.to_dict(self.sku)
                for template in self.workshop_templates
                if device_profile is None or profile_supports_workflow(profile, CapabilityWorkflow.WORKSHOP)
            ],
            "workflows": frontend_release_capabilities(self.sku, profile=device_profile),
            "supports": {
                name: state
                if device_profile is None
                or profile_supports_workflow(profile, CapabilityWorkflow(name), model=self.sku)
                else CapabilityState.UNSUPPORTED.value
                for name, state in self.supports.to_dict().items()
            },
            **(
                {"native_diy_templates": [template.to_dict() for template in self.native_diy_templates]}
                if self.native_diy_templates
                and (
                    device_profile is None
                    or profile_supports_workflow(profile, CapabilityWorkflow.ADVANCED, model=self.sku)
                )
                else {}
            ),
            **({"diy_slot_policy": self.diy_slot_policy} if self.diy_slot_policy != "fixed" else {}),
            **({"advanced_create": False} if not self.advanced_create else {}),
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
            "apply": {
                name: state
                if device_profile is None or profile_supports_workflow(profile, CapabilityWorkflow(name))
                else CapabilityState.UNSUPPORTED.value
                for name, state in self.apply.to_dict().items()
            },
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

# Exact H6102 goods-18 roster: Android 7.6.01 dreamcolorlightv1.adjust.Diy.e.
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
        source_reference="Android 7.6.01 dreamcolorlightv1.adjust.Diy.e, H6102 goods 18",
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

# Android 7.6.01 pact_h6099/detail/diy/H66A0DiyConfig, goods 327.
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
        source_reference="Android 7.6.01 H66A0DiyConfig.getBasicEffectList/getMixEffectList",
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

# Android 7.6.01 h61d3/adjustNew/diy/H1A42DiyConfig, goods 400.
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
        source_reference="Android 7.6.01 H1A42DiyConfig.getBasicEffectList/getMixEffectList",
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

# Android 7.6.01 h61d3/adjustNew/diy/H61F6DiyConfig, goods 261.
H61F5_DIY_FAMILIES: Final = tuple(
    replace(
        family,
        source_reference="Android 7.6.01 H61F6DiyConfig.getBasicEffectList/getMixEffectList",
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
        source_reference="Android 7.6.01 H7025DiyConfig.getBasicEffectList/getMixEffectList",
    )
    for family in H7020_DIY_FAMILIES[:6]
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
        source_reference="Android 7.6.01 H6072DiyNewConfig.getBasicEffectList/getMixEffectList, H6076 goods 69",
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


def _single_template(
    model: str,
    family: DiyEffectFamily,
    *,
    grammar: str | None = None,
) -> CatalogueTemplate:
    variation = family.variations[0]
    content: EffectContent
    grammar = get_profile(model).effect_grammar if grammar is None else grammar
    if grammar in {"H617A", "H6099"}:
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
# ScenesOp.changeEffectStr4Sku uses 60 for H6102 presets 504/506. This is
# preset construction evidence, not permission to infer runtime physical geometry.
# DiyColorParams.Companion.a() supplies the app's seven-colour defaults;
# raw ParamsV2 carrier seeds do not themselves satisfy the editor's bounds.
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
H617C_NATIVE_DIY_TEMPLATES: Final = _rgbic_native_templates(30)
H617A_CATALOGUE_TEMPLATES: Final = (
    *_h617a_catalogue_templates("H617A", H617A_NATIVE_MUSIC_MODES),
    *H617A_NATIVE_DIY_TEMPLATES,
)
H617E_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617E")
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
H617C_DIY_FAMILIES: Final = tuple(
    replace(family, source_reference="H617C DreamColor basic and mixed DIY") for family in H6125_DIY_FAMILIES
)
H617C_NATIVE_MUSIC_MODES: Final = _native_music_modes("H617C")
# The selector order follows the app, not the wire codes.
H6076_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H6076"].music_modes
)
H7025_NATIVE_MUSIC_MODES: Final = tuple(
    NativeModeOption(slug, _mode_label(slug)) for slug in MODEL_PROFILES["H7025"].music_modes
)

H60A1_DIY_FAMILIES: Final = tuple(
    replace(family, palette_max=8, source_reference="H60A1 #402")
    for family in H617A_TYPE04_FAMILIES
    if family.family in (0, 1, 2, 3, 8, 9, 10)
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
        supports=CatalogueSupport(
            multi=workflow_capability_state(model, CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state(model, CapabilityWorkflow.ADVANCED),
            workshop=CapabilityState.UNSUPPORTED,
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state(model, CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state(model, CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state(model, CapabilityWorkflow.MULTI),
            palette_diy=CapabilityState.UNSUPPORTED,
            workshop=CapabilityState.UNSUPPORTED,
        ),
        advanced_create=False,
        temporary_diy_selector=254,
        native_actions=tuple(
            NativeModeOption(str(int(action)), f"Native action {int(action)}") for action in H60a6PaintBody.ActionCode
        )
        if native
        else (),
    )


MODEL_EFFECT_CATALOGUES: Final = {
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6102", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6102", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6102", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6102", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6102", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6102", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6102", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6102", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6097", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6097", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6097", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6097", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6097", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6097", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6097", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6097", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H66A0", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H66A0", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H66A0", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H66A0", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H66A0", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H66A0", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H66A0", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H66A0", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H1A42", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H1A42", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H1A42", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H1A42", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H1A42", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H1A42", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H1A42", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H1A42", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H61F5", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H61F5", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H61F5", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H61F5", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H61F5", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H61F5", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H61F5", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H61F5", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6125", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6125", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6125", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6125", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6125", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6125", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6125", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6125", CapabilityWorkflow.WORKSHOP),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H617C", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H617C", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H617C", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H617C", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H617C", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H617C", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H617C", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H617C", CapabilityWorkflow.WORKSHOP),
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
    "H6179": ModelEffectCatalogue(
        sku="H6179",
        painted_effects=(),
        effects=H6179_DIY_FAMILIES,
        music_modes=H6179_NATIVE_MUSIC_MODES,
        video_modes=(),
        templates=H6179_CATALOGUE_TEMPLATES,
        workshop_templates=(),
        diy_slot_policy="approved_observed",
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6179", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6179", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6179", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6179", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6179", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6179", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6179", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6179", CapabilityWorkflow.WORKSHOP),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H6076", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H6076", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H6076", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H6076", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H6076", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H6076", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H6076", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H6076", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H7020", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H7020", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H7020", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H7020", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H7020", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H7020", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H7020", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H7020", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H7025", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H7025", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H7025", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H7025", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H7025", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H7025", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H7025", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H7025", CapabilityWorkflow.WORKSHOP),
        ),
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
        supports=CatalogueSupport(
            multi=workflow_capability_state("H601C", CapabilityWorkflow.MULTI),
            advanced=workflow_capability_state("H601C", CapabilityWorkflow.ADVANCED),
            workshop=workflow_capability_state("H601C", CapabilityWorkflow.WORKSHOP),
        ),
        apply=ApplySupport(
            painted=studio_apply_capability_state("H601C", CapabilityWorkflow.PAINTED),
            single=studio_apply_capability_state("H601C", CapabilityWorkflow.SINGLE),
            multi=studio_apply_capability_state("H601C", CapabilityWorkflow.MULTI),
            palette_diy=studio_apply_capability_state("H601C", CapabilityWorkflow.PALETTE_DIY),
            workshop=studio_apply_capability_state("H601C", CapabilityWorkflow.WORKSHOP),
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
    profile = get_profile(model) if profile is None else profile
    if get_profile(model).supports_custom_effects and not profile.supports_custom_effects:
        raise ValueError(f"{model} effective profile does not support custom effects")
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    if catalogue is None:
        raise ValueError(f"{model} has no custom-effect catalogue")
    if isinstance(content, PaintedEffect):
        if content.effect not in {effect["id"] for effect in catalogue.painted_effects}:
            raise ValueError(f"{model} painted effect {content.effect!r} is not supported")
        profile = get_profile(model) if profile is None else profile
        if profile.effect_grammar != get_profile(model).effect_grammar:
            raise ValueError(f"{model} effective profile has a different effect grammar")
        physical = catalogue.painted_addressing == "physical_ic"
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
            rate_min = family.multi_rate_min if multi and family.multi_rate_min is not None else family.rate_min
            if not rate_min <= content.speed <= family.rate_max:
                raise ValueError(f"{model} family {pair.family} {family.rate} is outside catalogue limits")
    if (
        isinstance(content, PaintedEffect | MultiEffect)
        and not catalogue.speed_min <= content.speed <= catalogue.speed_max
    ):
        raise ValueError(f"{model} speed is outside catalogue limits")


def validate_native_diy(content: LayeredEffect, model: str, profile: ModelProfile) -> bool:
    """Only geometry-dependent edits need IC metadata; APK seeds remain presets."""
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    if catalogue is None or profile.effect_grammar != "H617A":
        raise ValueError("native DIY templates require an exact compatible catalogue")
    contract = next(
        (contract for contract in catalogue.native_diy_templates if contract.template_id == content.native_diy),
        None,
    )
    if contract is not None:
        _validate_h7020_native_diy(content, catalogue, contract)
        return False
    template = next(
        (
            t
            for t in catalogue.templates
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
    # NewConfigManager + ParamsV2 split app palettes round-robin across these layers.
    for selector, indices, minimum, maximum in catalogue.native_diy_palette_groups:
        if selector != content.native_diy:
            continue
        if selector == 506 and indices == (2, 3):
            # ParamsV2:1185-1227: split two-way palette, or one active full-strip
            # layer plus a black single-IC layer. DiyTemp4BloomV1:88-95: 2..8 each.
            moving = content.layers[2:]
            original_moving = seed.layers[2:]
            geometry_changed = any(
                (layer.area, layer.selection, layer.selected_movement.direction)
                != (original.area, original.selection, original.selected_movement.direction)
                for layer, original in zip(moving, original_moving, strict=True)
            )
            if geometry_changed and profile.physical_ic_count is None:
                raise ValueError("this native DIY geometry edit requires a known physical IC count")
            count = profile.physical_ic_count if geometry_changed else original_moving[0].selection.quantity * 2
            assert count is not None
            topology = tuple(
                (
                    layer.area.start_tenths,
                    layer.area.width_tenths,
                    layer.selection.type,
                    layer.selection.quantity,
                    layer.selected_movement.direction,
                )
                for layer in moving
            )
            if not all(layer.selected_movement.enabled and layer.selected_movement.enter_exit for layer in moving):
                raise ValueError("Bloom movement must retain its APK direction topology")
            if topology == ((0, 5, 1, count // 2, 0), (5, 5, 1, count // 2, 2)):
                pass
            elif any(topology == ((0, 0, 1, count, direction), (0, 0, 1, 1, direction)) for direction in (0, 2)):
                if moving[1].palette != ((0, 0, 0),):
                    raise ValueError("Bloom one-way inactive layer must contain one black colour")
                indices = (2,)
            else:
                raise ValueError("Bloom movement must retain its APK direction topology")
        sizes = tuple(len(content.layers[index].palette) for index in indices)
        total = sum(sizes)
        if not minimum <= total <= maximum or sizes != tuple(
            (total + len(indices) - index - 1) // len(indices) for index in range(len(indices))
        ):
            raise ValueError(
                f"native DIY {selector} palette group requires {minimum} to {maximum} colours split evenly"
            )
    geometry_edited = False
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
        geometry_edited |= dependent
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
    return geometry_edited


def _template_available(template: CatalogueTemplate, profile: ModelProfile) -> bool:
    content = template.content
    if isinstance(content, MusicProfile):
        return content.mode in profile.music_modes
    if isinstance(content, VideoProfile):
        return content.mode in profile.video_modes
    if isinstance(content, PaintedEffect):
        workflow = CapabilityWorkflow.PAINTED
    elif isinstance(content, LayeredEffect):
        workflow = CapabilityWorkflow.ADVANCED
    elif isinstance(content, NativeEffect):
        workflow = (
            CapabilityWorkflow.PAINTED
            if content.family == 798
            else CapabilityWorkflow.ADVANCED
            if content.preset_id in (11, 12)
            else CapabilityWorkflow.SINGLE
        )
    elif isinstance(content, SingleEffect | H6179SingleDiyEffect):
        workflow = CapabilityWorkflow.SINGLE
    elif isinstance(content, MultiEffect | H6179MixedDiyEffect):
        workflow = CapabilityWorkflow.MULTI
    elif isinstance(content, PaletteDiyEffect):
        workflow = CapabilityWorkflow.PALETTE_DIY
    elif isinstance(content, WorkshopEffect):
        workflow = CapabilityWorkflow.WORKSHOP
    else:
        raise ValueError("unsupported catalogue template content")
    return profile_supports_workflow(profile, workflow)


def _template_for_profile(template: CatalogueTemplate, profile: ModelProfile | None) -> CatalogueTemplate:
    if profile is None:
        return template
    content = template.content
    if isinstance(content, MusicProfile):
        variant = music_variant(profile, music_code_for(content.model, content.mode, profile=profile))
        return replace(
            template,
            content=replace(
                content,
                sensitivity=profile.music_sensitivity_max,
                calm=variant.calm_default if variant and variant.supports_style else None,
            ),
        )
    if (
        isinstance(content, PaintedEffect)
        and content.addressing == "physical_ic"
        and profile.physical_ic_count is not None
    ):
        return replace(template, content=replace(content, segments=(None,) * profile.physical_ic_count))
    return template


def _validate_h7020_native_diy(
    content: LayeredEffect,
    catalogue: ModelEffectCatalogue,
    contract: NativeDiyTemplateContract,
) -> None:
    template = next(
        (
            template.content
            for template in catalogue.templates
            if isinstance(template.content, LayeredEffect) and template.content.native_diy == contract.template_id
        ),
        None,
    )
    if not isinstance(template, LayeredEffect):
        raise ValueError("unknown native DIY template")
    if len(content.layers) != contract.layer_count:
        raise ValueError(f"native DIY {contract.template_id} must retain {contract.layer_count} layers")
    palettes = tuple(layer.palette for layer in content.layers)
    template_palettes = tuple(layer.palette for layer in template.layers)
    palette_changed = palettes != template_palettes
    if palette_changed and not all(palette == palettes[0] for palette in palettes[1:]):
        raise ValueError(f"native DIY {contract.template_id} must use one shared palette")
    if palette_changed and not contract.palette_min <= len(palettes[0]) <= contract.palette_max:
        raise ValueError(
            f"native DIY {contract.template_id} palette must contain "
            f"{contract.palette_min} to {contract.palette_max} colours"
        )
    if contract.rate_field == "selected_movement_speed":
        rates = tuple(layer.selected_movement.speed for layer in content.layers)
        expected = replace(
            template,
            layers=tuple(
                replace(
                    layer,
                    palette=palettes[0] if palette_changed else layer.palette,
                    selected_movement=replace(layer.selected_movement, speed=rates[0]),
                )
                for layer in template.layers
            ),
        )
    else:
        rates = tuple(
            value
            for layer in content.layers
            for value in (layer.colour_speed, *(pattern.change_speed for pattern in layer.brightness_patterns))
        )
        expected = replace(
            template,
            layers=tuple(
                replace(
                    layer,
                    palette=palettes[0] if palette_changed else layer.palette,
                    colour_speed=rates[0],
                    brightness_patterns=tuple(
                        replace(pattern, change_speed=rates[0]) for pattern in layer.brightness_patterns
                    ),
                )
                for layer in template.layers
            ),
        )
    if not rates or any(rate != rates[0] for rate in rates):
        raise ValueError(f"native DIY {contract.template_id} must use one shared rate")
    if not contract.rate_min <= rates[0] <= contract.rate_max:
        raise ValueError(
            f"native DIY {contract.template_id} rate must be from {contract.rate_min} to {contract.rate_max}"
        )
    if content != expected:
        raise ValueError(f"native DIY {contract.template_id} only supports palette and rate edits")


def native_diy_template_contract(model: str, template_id: int | None) -> NativeDiyTemplateContract | None:
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    if catalogue is None:
        return None
    return next(
        (contract for contract in catalogue.native_diy_templates if contract.template_id == template_id),
        None,
    )


def requires_approved_diy_slot(model: str) -> bool:
    catalogue = MODEL_EFFECT_CATALOGUES.get(model)
    return catalogue is not None and catalogue.diy_slot_policy == "approved_observed"


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
            if profile is not None and not _template_available(template, profile):
                raise ValueError("Device profile does not support this effect template")
            if isinstance(template.content, PaintedEffect) and template.content.addressing == "physical_ic":
                count = (get_profile(model) if profile is None else profile).physical_ic_count
                if count is None:
                    raise ValueError(f"{model} graffiti requires a known physical IC count")
            return _template_for_profile(template, get_profile(model) if profile is None else profile)
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
        isinstance(canonical, NativeEffect)
        and isinstance(content, NativeEffect)
        and (content.model, content.family, content.preset_id, content.template)
        == (canonical.model, canonical.family, canonical.preset_id, canonical.template)
        or isinstance(canonical, PaintedEffect)
        and isinstance(content, PaintedEffect)
        and canonical.addressing == content.addressing
        or isinstance(canonical, SingleEffect)
        and isinstance(content, SingleEffect)
        and (content.family, content.variant) == (canonical.family, canonical.variant)
        or isinstance(canonical, H6179SingleDiyEffect)
        and isinstance(content, H6179SingleDiyEffect)
        and (content.model, content.family, content.variant) == (canonical.model, canonical.family, canonical.variant)
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
