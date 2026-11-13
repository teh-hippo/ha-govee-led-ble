"""Effect Studio catalogue validation and template resolution."""

from __future__ import annotations

from dataclasses import replace
from typing import Final

from .const import ModelProfile, get_profile, supported_effect_categories
from .effect_catalogue_families import DEFAULT_PALETTE as DEFAULT_PALETTE
from .effect_catalogue_families import H1A42_DIY_FAMILIES as H1A42_DIY_FAMILIES
from .effect_catalogue_families import H60A1_DIY_FAMILIES as H60A1_DIY_FAMILIES
from .effect_catalogue_families import H60B2_DIY_FAMILIES as H60B2_DIY_FAMILIES
from .effect_catalogue_families import H61F5_DIY_FAMILIES as H61F5_DIY_FAMILIES
from .effect_catalogue_families import H66A0_DIY_FAMILIES as H66A0_DIY_FAMILIES
from .effect_catalogue_families import H600A_DIY_FAMILIES as H600A_DIY_FAMILIES
from .effect_catalogue_families import H601C_DIY_FAMILIES as H601C_DIY_FAMILIES
from .effect_catalogue_families import H605C_DIY_FAMILIES as H605C_DIY_FAMILIES
from .effect_catalogue_families import H607C_DIY_FAMILIES as H607C_DIY_FAMILIES
from .effect_catalogue_families import H607C_NATIVE_MUSIC_MODES as H607C_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H617A_NATIVE_MUSIC_MODES as H617A_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H617A_PAINTED_EFFECTS as H617A_PAINTED_EFFECTS
from .effect_catalogue_families import H617A_TYPE04_APPLY_CODE as H617A_TYPE04_APPLY_CODE
from .effect_catalogue_families import H617A_TYPE04_FAMILIES as H617A_TYPE04_FAMILIES
from .effect_catalogue_families import H617A_WORKSHOP_APPLY_CODE as H617A_WORKSHOP_APPLY_CODE
from .effect_catalogue_families import H617A_WORKSHOP_SCENE_TYPE as H617A_WORKSHOP_SCENE_TYPE
from .effect_catalogue_families import H617C_DIY_FAMILIES as H617C_DIY_FAMILIES
from .effect_catalogue_families import H617C_NATIVE_MUSIC_MODES as H617C_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H617E_NATIVE_MUSIC_MODES as H617E_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H619A_DIY_FAMILIES as H619A_DIY_FAMILIES
from .effect_catalogue_families import H619A_NATIVE_MUSIC_MODES as H619A_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6046_DIY_FAMILIES as H6046_DIY_FAMILIES
from .effect_catalogue_families import H6072_DIY_FAMILIES as H6072_DIY_FAMILIES
from .effect_catalogue_families import H6072_NATIVE_MUSIC_MODES as H6072_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6076_DIY_FAMILIES as H6076_DIY_FAMILIES
from .effect_catalogue_families import H6076_NATIVE_MUSIC_MODES as H6076_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6097_DIY_FAMILIES as H6097_DIY_FAMILIES
from .effect_catalogue_families import H6099_DIY_APPLY_CODE as H6099_DIY_APPLY_CODE
from .effect_catalogue_families import H6099_DIY_FAMILIES as H6099_DIY_FAMILIES
from .effect_catalogue_families import H6102_DIY_FAMILIES as H6102_DIY_FAMILIES
from .effect_catalogue_families import H6117_DIY_FAMILIES as H6117_DIY_FAMILIES
from .effect_catalogue_families import H6117_NATIVE_MUSIC_MODES as H6117_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6125_DIY_FAMILIES as H6125_DIY_FAMILIES
from .effect_catalogue_families import H6125_NATIVE_MUSIC_MODES as H6125_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6179_DIY_FAMILIES as H6179_DIY_FAMILIES
from .effect_catalogue_families import H6179_DIY_SOURCE_REFERENCE as H6179_DIY_SOURCE_REFERENCE
from .effect_catalogue_families import H6179_NATIVE_MUSIC_MODES as H6179_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6181_DIY_FAMILIES as H6181_DIY_FAMILIES
from .effect_catalogue_families import H6199_DIY_SOURCE_REFERENCE as H6199_DIY_SOURCE_REFERENCE
from .effect_catalogue_families import H6199_NATIVE_MUSIC_MODES as H6199_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H6199_PALETTE_DIY_APPLY_CODE as H6199_PALETTE_DIY_APPLY_CODE
from .effect_catalogue_families import H6199_PALETTE_DIY_APPLY_MUSIC_CODE as H6199_PALETTE_DIY_APPLY_MUSIC_CODE
from .effect_catalogue_families import H6199_PALETTE_DIY_FAMILIES as H6199_PALETTE_DIY_FAMILIES
from .effect_catalogue_families import H6199_VIDEO_MODES as H6199_VIDEO_MODES
from .effect_catalogue_families import H6199_WORKSHOP_APPLY_CODE as H6199_WORKSHOP_APPLY_CODE
from .effect_catalogue_families import H6199_WORKSHOP_APPLY_MUSIC_CODE as H6199_WORKSHOP_APPLY_MUSIC_CODE
from .effect_catalogue_families import H7020_DIY_FAMILIES as H7020_DIY_FAMILIES
from .effect_catalogue_families import H7020_NATIVE_MUSIC_MODES as H7020_NATIVE_MUSIC_MODES
from .effect_catalogue_families import H7025_DIY_FAMILIES as H7025_DIY_FAMILIES
from .effect_catalogue_families import H7025_NATIVE_MUSIC_MODES as H7025_NATIVE_MUSIC_MODES
from .effect_catalogue_families import _native_music_modes as _native_music_modes
from .effect_catalogue_models import CatalogueTemplate as CatalogueTemplate
from .effect_catalogue_models import DiyEffectFamily as DiyEffectFamily
from .effect_catalogue_models import DiyEffectVariation as DiyEffectVariation
from .effect_catalogue_models import ModelEffectCatalogue as ModelEffectCatalogue
from .effect_catalogue_models import NativeDiyTemplateContract as NativeDiyTemplateContract
from .effect_catalogue_models import NativeModeOption as NativeModeOption
from .effect_catalogue_models import WorkshopTemplate as WorkshopTemplate
from .effect_catalogue_models import _template_available, _template_for_profile
from .effect_catalogue_registry import MODEL_EFFECT_CATALOGUES as MODEL_EFFECT_CATALOGUES
from .effect_catalogue_templates import _H1771_SECTIONS, _h1771_rate_min
from .effect_catalogue_templates import H617A_CATALOGUE_TEMPLATES as H617A_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import H617A_NATIVE_DIY_SEEDS as H617A_NATIVE_DIY_SEEDS
from .effect_catalogue_templates import H617A_NATIVE_DIY_TEMPLATES as H617A_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H617C_NATIVE_DIY_TEMPLATES as H617C_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H617E_CATALOGUE_TEMPLATES as H617E_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import H619A_NATIVE_DIY_TEMPLATES as H619A_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H6102_NATIVE_DIY_TEMPLATES as H6102_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H6117_NATIVE_DIY_TEMPLATES as H6117_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H6125_NATIVE_DIY_TEMPLATES as H6125_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H6179_CATALOGUE_TEMPLATES as H6179_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import H6199_CATALOGUE_TEMPLATES as H6199_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import H7020_CATALOGUE_TEMPLATES as H7020_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import H7020_NATIVE_DIY_CONTRACTS as H7020_NATIVE_DIY_CONTRACTS
from .effect_catalogue_templates import H7020_NATIVE_DIY_SEEDS as H7020_NATIVE_DIY_SEEDS
from .effect_catalogue_templates import H7020_NATIVE_DIY_TEMPLATES as H7020_NATIVE_DIY_TEMPLATES
from .effect_catalogue_templates import H7025_CATALOGUE_TEMPLATES as H7025_CATALOGUE_TEMPLATES
from .effect_catalogue_templates import WORKSHOP_PROTOCOL_FIXTURES as WORKSHOP_PROTOCOL_FIXTURES
from .effect_catalogue_templates import _single_template as _single_template
from .effect_domain import (
    EffectContent,
    EffectValidationError,
    H6179SingleDiyEffect,
    JsonValue,
    LayeredEffect,
    MultiEffect,
    MusicProfile,
    NativeEffect,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
    VideoProfile,
)
from .native_effect import NativeDiyLayer, NativeOpaqueLayer

EFFECT_STUDIO_CATALOGUE_SCHEMA_VERSION: Final = 12
LEGACY_CATALOGUE_SKU: Final = "H617A"


def validate_effect_eligibility(
    content: PaintedEffect | SingleEffect | MultiEffect | PaletteDiyEffect | NativeEffect,
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
    if isinstance(content, NativeEffect):
        if model == "H60B0":
            from .h60b0_diy import validate_h60b0_diy

            validate_h60b0_diy(content, profile.native_effect_revision)
            return
        if model == "H1771" and content.model == model and profile.effect_grammar == "H1771":
            if not any(isinstance(layer, NativeDiyLayer) and layer.enabled for layer in content.layers):
                raise ValueError("select at least one native effect section")
            for index, layer in enumerate(content.layers):
                if isinstance(layer, NativeOpaqueLayer):
                    if content.template is None:
                        raise ValueError("unqualified native section cannot be authored")
                    continue
                if not isinstance(layer, NativeDiyLayer):
                    raise ValueError("unsupported native effect section")
                if not layer.enabled:
                    continue
                matches = [seed for _label, seed in _H1771_SECTIONS[index] if seed.kind == layer.kind]
                if not matches:
                    raise ValueError("native effect is not available in this section")
                temperature = not matches[0].palette
                if temperature:
                    if not 1000 <= layer.angle <= 10000 or not 0 <= layer.parameter <= 100:
                        raise ValueError("native colour temperature or brightness is outside the supported range")
                elif not 1 <= len(layer.palette) <= 8 or not any(
                    (layer.parameter, layer.flag) == (seed.parameter, seed.flag) for seed in matches
                ):
                    if content.template is None:
                        raise ValueError("native effect palette or variation is unsupported")
                if layer.speed < _h1771_rate_min(index, layer.kind):
                    if content.template is None:
                        raise ValueError("native effect speed must be at least one")
            return
        if content.model != model or profile.effect_grammar not in {"H607C", "H60B2"}:
            raise ValueError("native zone content does not match the effective profile")
        if not any(isinstance(layer, NativeDiyLayer) and layer.enabled for layer in content.layers):
            raise ValueError("select at least one native effect section")
        for layer in content.layers:
            if isinstance(layer, NativeOpaqueLayer) or not isinstance(layer, NativeDiyLayer):
                raise ValueError("unqualified native zone parameters cannot be authored")
            if not layer.enabled:
                continue
            family = next((family for family in catalogue.effects if family.family == layer.kind), None)
            if family is None or layer.parameter not in {variation.variant for variation in family.variations}:
                raise ValueError("native DIY family or variation is unsupported")
            if not (family.palette_min or 1) <= len(layer.palette) <= (family.palette_max or catalogue.palette_max):
                raise ValueError("native DIY palette is outside its variant bounds")
            if family.secondary_palette_min is None:
                if layer.secondary_palette:
                    raise ValueError("this native effect has no secondary palette")
            elif (
                not family.secondary_palette_min <= len(layer.secondary_palette) <= (family.secondary_palette_max or 0)
            ):
                raise ValueError("native secondary palette is outside its variant bounds")
            if not family.rate_min <= layer.speed <= family.rate_max:
                raise ValueError("native DIY rate is outside its variant bounds")
        return
    if isinstance(content, PaintedEffect):
        if content.model is not None and content.model != model:
            raise ValueError("painted effect identity does not match the target model")
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
        if profile.effect_grammar == "H607C":
            raise ValueError("native DIY requires its independently bounded zone definition")
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
    """Only geometry-dependent edits need IC metadata; native seeds remain presets."""
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
    # Palettes are split round-robin across these layers.
    for selector, indices, minimum, maximum in catalogue.native_diy_palette_groups:
        if selector != content.native_diy:
            continue
        if selector == 506 and indices == (2, 3):
            # Split two-way palette, or one active full-strip
            # layer plus a black single-IC layer; 2..8 colours each.
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
                raise ValueError("Bloom movement must retain its direction topology")
            if topology == ((0, 5, 1, count // 2, 0), (5, 5, 1, count // 2, 2)):
                pass
            elif any(topology == ((0, 0, 1, count, direction), (0, 0, 1, 1, direction)) for direction in (0, 2)):
                if moving[1].palette != ((0, 0, 0),):
                    raise ValueError("Bloom one-way inactive layer must contain one black colour")
                indices = (2,)
            else:
                raise ValueError("Bloom movement must retain its direction topology")
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
                raise ValueError("Sky star size is outside physical-IC bounds")
            if (
                content.native_diy == 503
                and len(layer.palette) != len(original.palette)
                and len(layer.palette) > min(max(1, count * 2 // 10), 8)
            ):
                raise ValueError("Meteor palette is outside physical-IC bounds")
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
        and (content.model, content.family, content.preset_id, content.template, content.revision)
        == (canonical.model, canonical.family, canonical.preset_id, canonical.template, canonical.revision)
        or isinstance(canonical, PaintedEffect)
        and isinstance(content, PaintedEffect)
        and (canonical.addressing, canonical.model) == (content.addressing, content.model)
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
