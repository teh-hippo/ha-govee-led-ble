"""Effect Studio catalogue contracts and profile-aware presentation."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace

from .const import MODEL_PROFILES, ModelProfile, supported_effect_categories
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
    JsonValue,
    LayeredEffect,
    MultiEffect,
    MusicProfile,
    NativeEffect,
    PaintedEffect,
    PaletteDiyEffect,
    RetainedSceneEffect,
    SingleEffect,
    TypedMixedDiyEffect,
    TypedSingleDiyEffect,
    VideoProfile,
    effect_content_to_dict,
)
from .layered_scene_decoder import decode_workshop_effect
from .music_commands import music_default_available
from .music_protocol import music_code_for
from .music_semantics import music_parameters_available, music_params_for_mode, music_variant
from .protocol_music_params import music_default_palette


@dataclass(frozen=True, slots=True)
class DiyEffectVariation:
    id: str
    label: str
    variant: int
    shared_identity: str | None = None

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
    source_reference: str = "DIY roster"
    category: str = "single_layer"
    rate_min: int = 0
    rate_max: int = 100
    palette_max: int | None = None
    multi_rate_min: int | None = None
    palette_min: int | None = None
    secondary_palette_min: int | None = None
    secondary_palette_max: int | None = None
    palette_labels: tuple[str, str] | None = None

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
            **({"palette_min": self.palette_min} if self.palette_min is not None else {}),
            **(
                {"secondary_palette": {"min": self.secondary_palette_min, "max": self.secondary_palette_max}}
                if self.secondary_palette_min is not None
                else {}
            ),
            **({"palette_labels": list(self.palette_labels)} if self.palette_labels is not None else {}),
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

    def content(self, model: str) -> RetainedSceneEffect:
        raw_param = base64.b64decode(self.raw_param_b64, validate=True)
        effect, trailing_padding = decode_workshop_effect(model, raw_param)
        return RetainedSceneEffect(
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
    rate_min: int | None = None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "content": effect_content_to_dict(self.content),
            **({"rate_min": self.rate_min} if self.rate_min is not None else {}),
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
    activation_selector: int | None = None

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
class ModelEffectCatalogue:
    sku: str
    painted_effects: tuple[dict[str, str], ...]
    effects: tuple[DiyEffectFamily, ...]
    music_modes: tuple[NativeModeOption, ...]
    video_modes: tuple[NativeModeOption, ...]
    templates: tuple[CatalogueTemplate, ...]
    workshop_templates: tuple[WorkshopTemplate, ...]
    palette_min: int = 1
    palette_max: int = 8
    multi_max: int = MAX_MULTI_EFFECTS
    speed_min: int = 0
    speed_max: int = 100
    brightness_min: int = 0
    brightness_max: int = 100
    painted_addressing: str = "segments"
    painted_background: tuple[int, int, int] = (0, 0, 0)
    # Exact-model authoring bounds; wire grammar alone does not qualify them.
    native_diy_palette_groups: tuple[tuple[int, tuple[int, ...], int, int], ...] = ()
    native_diy_templates: tuple[NativeDiyTemplateContract, ...] = ()
    diy_destination_policy: str = "fixed"
    diy_destination_min: int = 0
    diy_destination_max: int = 0xFFFF
    advanced_create: bool = True
    temporary_diy_selector: int | None = None
    native_actions: tuple[NativeModeOption, ...] = ()
    native_zones: tuple[tuple[str, int, int | None], ...] = ()
    music_zone_modes: tuple[tuple[str, tuple[str, ...]], ...] = ()
    auxiliary_music_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.diy_destination_policy not in {"fixed", "explicit_destination"}:
            raise ValueError("DIY destination policy must be fixed or explicit_destination")
        if (
            not isinstance(self.diy_destination_min, int)
            or isinstance(self.diy_destination_min, bool)
            or not isinstance(self.diy_destination_max, int)
            or isinstance(self.diy_destination_max, bool)
            or not 0 <= self.diy_destination_min <= self.diy_destination_max <= 0xFFFF
        ):
            raise ValueError("DIY destination bounds must be an ordered unsigned 16-bit range")

    def effects_for_profile(self, profile: ModelProfile) -> tuple[DiyEffectFamily, ...]:
        if profile.diy_family_variants is None:
            return self.effects
        allowed = dict(profile.diy_family_variants)
        return tuple(
            replace(
                effect,
                variations=tuple(
                    variation for variation in effect.variations if variation.variant in allowed[effect.family]
                ),
                palette_max=min(effect.palette_max or self.palette_max, profile.diy_palette_max or self.palette_max),
            )
            for effect in self.effects
            if effect.family in allowed
        )

    def templates_for_profile(self, profile: ModelProfile | None) -> tuple[CatalogueTemplate, ...]:
        return tuple(
            _template_for_profile(template, profile)
            for template in self.templates
            if profile is None or _template_available(template, profile, self.sku)
        )

    def to_dict(self, *, profile: ModelProfile | None = None) -> dict[str, JsonValue]:
        device_profile = profile
        profile = MODEL_PROFILES[self.sku] if profile is None else profile
        effects_enabled = profile.command_operations is None or bool(
            supported_effect_categories(self.sku, profile=profile)
        )
        music_profile = (
            replace(profile, music_modes=(*profile.music_modes, *self.auxiliary_music_modes))
            if self.auxiliary_music_modes and profile.music_modes
            else profile
        )
        zones = profile.native_zones or self.native_zones
        result: dict[str, JsonValue] = {
            "sku": self.sku,
            **(
                {
                    "native_zones": [
                        {
                            "id": name,
                            "label": name.capitalize(),
                            "segment_count": logical,
                            "physical_ic_budget": physical,
                        }
                        for name, logical, physical in zones
                    ]
                }
                if zones
                else {}
            ),
            **(
                {"music_zone_modes": {name: list(modes) for name, modes in self.music_zone_modes}}
                if self.music_zone_modes
                else {}
            ),
            **({"native_actions": [action.to_dict() for action in self.native_actions]} if self.native_actions else {}),
            "painted_effects": [
                dict(effect)
                for effect in self.painted_effects
                if effects_enabled
                and (
                    device_profile is None
                    or profile_supports_workflow(profile, CapabilityWorkflow.PAINTED, model=self.sku)
                )
            ],
            **(
                {"painted_addressing": self.painted_addressing, "painted_background": list(self.painted_background)}
                if self.painted_addressing != "segments"
                else {}
            ),
            "effects": [
                effect.to_dict()
                for effect in self.effects_for_profile(profile)
                if effects_enabled
                and (
                    device_profile is None
                    or profile_supports_workflow(profile, CapabilityWorkflow.SINGLE, model=self.sku)
                )
            ],
            "music_modes": [
                mode.to_dict() for mode in self.music_modes if effects_enabled and mode.id in profile.music_modes
            ],
            "music_settings": {
                mode.id: _music_mode_settings(self.sku, mode.id, music_profile)
                for mode in self.music_modes
                if effects_enabled and mode.id in music_profile.music_modes
            },
            "video_modes": [mode.to_dict() for mode in self.video_modes if effects_enabled],
            "video_settings": list(_video_profile_settings(profile)),
            "video_controls": {
                "saturation_min": profile.video_saturation_min,
                "softness_min": profile.video_softness_min,
                "softness_max": profile.video_softness_max,
                "video_sensitivity": {
                    "minimum": profile.video_sensitivity_min,
                    "maximum": profile.video_sensitivity_max,
                    "default": 50,
                },
                "hdmi_input_count": profile.hdmi_input_count,
                "hdmi_box_effect_max": profile.hdmi_box_effect_max,
                "color_calibration": {
                    "minimum": profile.video_color_calibration_min,
                    "maximum": profile.video_color_calibration_max,
                    "default": [50, 50, 50],
                    "channels": [3, 4] if profile.supports_video_color_calibration else [],
                },
                "white_balance": {
                    "representation": profile.video_white_balance_representation,
                    "minimum": profile.video_white_balance_min,
                    "maximum": profile.video_white_balance_max,
                    "default": profile.video_white_balance_default,
                },
                "brightness_zones": list(profile.video_brightness_zones),
            },
            "templates": [
                template.to_dict() for template in self.templates_for_profile(device_profile) if effects_enabled
            ],
            "workshop_templates": [
                template.to_dict(self.sku)
                for template in self.workshop_templates
                if effects_enabled
                and (
                    device_profile is None
                    or profile_supports_workflow(profile, CapabilityWorkflow.WORKSHOP, model=self.sku)
                )
            ],
            "workflows": frontend_release_capabilities(self.sku, profile=device_profile) if effects_enabled else [],
            "supports": {
                name: workflow_capability_state(self.sku, CapabilityWorkflow(name), profile=device_profile).value
                if effects_enabled
                else CapabilityState.UNSUPPORTED.value
                for name in ("multi", "advanced", "workshop")
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
            **(
                {"diy_destination_policy": self.diy_destination_policy}
                if self.diy_destination_policy != "fixed"
                else {}
            ),
            **(
                {
                    "diy_destination_route": ":".join(
                        (
                            self.sku,
                            profile.effect_grammar or "",
                            profile.diy_upload_transport or "default",
                            "ack" if profile.diy_requires_upload_ack else "activation-only",
                        )
                    )
                }
                if self.diy_destination_policy == "explicit_destination"
                else {}
            ),
            **({"diy_destination_min": self.diy_destination_min} if self.diy_destination_min else {}),
            **({"diy_destination_max": self.diy_destination_max} if self.diy_destination_max != 0xFFFF else {}),
            **({"advanced_create": False} if not self.advanced_create else {}),
            "limits": {
                "palette_min": self.palette_min,
                "palette_max": profile.diy_palette_max or self.palette_max,
                "multi_max": self.multi_max,
                "speed_min": self.speed_min,
                "speed_max": self.speed_max,
                "brightness_min": self.brightness_min,
                "brightness_max": self.brightness_max,
                "music_sensitivity_min": profile.music_sensitivity_min,
                "music_sensitivity_max": profile.music_sensitivity_max,
            },
            "apply": {
                name: studio_apply_capability_state(self.sku, CapabilityWorkflow(name), profile=device_profile).value
                if effects_enabled
                else CapabilityState.UNSUPPORTED.value
                for name in ("painted", "single", "multi", "palette_diy", "workshop")
            },
        }
        return result


def _music_mode_settings(model: str, mode: str, profile: ModelProfile) -> dict[str, JsonValue]:
    code = music_code_for(model, mode, profile=profile)
    variant = music_variant(profile, code)
    available = music_default_available(model, mode, profile=profile)
    palette = music_default_palette(variant) if available and variant and variant.template else ()
    return {
        "available": available,
        "style": bool(variant and variant.supports_style),
        "calm_default": variant.calm_default if variant else False,
        "colour": bool(profile.supports_music_color and variant and variant.supports_fixed_colour),
        **(
            {"colour_default": list(variant.fixed_colour_default)}
            if variant and variant.fixed_colour_default is not None
            else {}
        ),
        "evidence": variant.evidence if variant else None,
        "palette_size": len(palette) if available else 0,
        **(
            {
                "palette": {
                    "min": variant.palette_bounds[0],
                    "max": variant.palette_bounds[1],
                    "default": [list(rgb) for rgb in palette],
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
            for spec in music_params_for_mode(code, profile)
        },
    }


def _video_profile_settings(profile: ModelProfile) -> tuple[str, ...]:
    return tuple(
        name
        for name, supported in (
            ("capture_region", profile.supports_video_capture_region),
            ("saturation", profile.supports_video_saturation),
            ("sound_effects", profile.supports_video_sound_effects),
            ("video_sensitivity", profile.supports_video_sensitivity),
            ("hdmi_input", profile.supports_hdmi_input),
            ("hdmi_box_light", profile.supports_hdmi_box_light),
            ("color_calibration", profile.supports_video_color_calibration),
            ("white_balance", profile.supports_white_balance),
            ("relative_brightness", profile.supports_relative_brightness or profile.video_embeds_relative_brightness),
            ("whole_relative_brightness", profile.supports_whole_relative_brightness),
            ("blank_screen", profile.supports_blank_screen),
            ("black_border", profile.supports_black_border),
        )
        if supported
    )


def _template_available(template: CatalogueTemplate, profile: ModelProfile, model: str) -> bool:
    content = template.content
    if isinstance(content, SingleEffect) and profile.diy_family_variants is not None:
        if content.variant not in dict(profile.diy_family_variants).get(content.family, ()):
            return False
    if isinstance(content, MusicProfile):
        return content.mode in profile.music_modes
    if isinstance(content, VideoProfile):
        return content.mode in profile.video_modes
    if isinstance(content, PaintedEffect):
        workflow = CapabilityWorkflow.PAINTED
    elif isinstance(content, LayeredEffect):
        workflow = CapabilityWorkflow.ADVANCED
    elif isinstance(content, NativeEffect):
        from .native_effect_codecs import native_effect_codec_for_profile

        codec = native_effect_codec_for_profile(profile)
        if codec is None or not codec.content_available_for_profile(content, profile):
            return False
        workflow = CapabilityWorkflow(content.workflow)
    elif isinstance(content, SingleEffect | TypedSingleDiyEffect):
        workflow = CapabilityWorkflow.SINGLE
    elif isinstance(content, MultiEffect | TypedMixedDiyEffect):
        workflow = CapabilityWorkflow.MULTI
    elif isinstance(content, PaletteDiyEffect):
        workflow = CapabilityWorkflow.PALETTE_DIY
    elif isinstance(content, RetainedSceneEffect):
        workflow = CapabilityWorkflow.WORKSHOP
    else:
        raise ValueError("unsupported catalogue template content")
    return profile_supports_workflow(profile, workflow, model=model)


def _template_for_profile(template: CatalogueTemplate, profile: ModelProfile | None) -> CatalogueTemplate:
    if profile is None:
        return template
    content = template.content
    if isinstance(content, SingleEffect) and profile.diy_palette_max is not None:
        return replace(
            template,
            content=replace(
                content,
                palette=content.palette[: profile.diy_palette_max],
            ),
        )
    if isinstance(content, MusicProfile):
        variant = music_variant(profile, music_code_for(content.model, content.mode, profile=profile))
        return replace(
            template,
            content=replace(
                content,
                sensitivity=profile.music_sensitivity_max,
                calm=variant.calm_default if variant and variant.supports_style else None,
                colour=content.colour
                if content.colour is not None
                else variant.fixed_colour_default
                if variant
                else None,
            ),
        )
    if (
        isinstance(content, PaintedEffect)
        and content.addressing == "physical_ic"
        and profile.physical_ic_count is not None
    ):
        return replace(template, content=replace(content, segments=(None,) * profile.physical_ic_count))
    return template
