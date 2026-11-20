"""Resolve immutable authoring content against a recipient's declared contract."""

from dataclasses import replace

from .const import ModelProfile, get_profile
from .effect_catalogue import LEGACY_CATALOGUE_SKU, MODEL_EFFECT_CATALOGUES
from .effect_catalogue_models import ModelEffectCatalogue
from .effect_domain import (
    EffectPair,
    H6179MixedDiyEffect,
    H6179SingleDiyEffect,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
    VideoProfile,
    WorkshopEffect,
)
from .music_protocol import music_code_for
from .music_semantics import compile_music_parameters, music_variant


def _target_pair(
    family: int, variant: int, source: ModelEffectCatalogue, target: ModelEffectCatalogue, profile: ModelProfile
) -> EffectPair:
    original = next((entry for entry in source.effects if entry.family == family), None)
    selection = next((entry for entry in original.variations if entry.variant == variant), None) if original else None
    matches = tuple(
        (recipient, entry)
        for recipient in target.effects_for_profile(profile)
        for entry in recipient.variations
        if original
        and selection
        and recipient.id == original.id
        and (entry.shared_identity or entry.id) == (selection.shared_identity or selection.id)
    )
    if len(matches) != 1 or original is None or original.rate != matches[0][0].rate:
        raise ValueError("The target has no equivalent effect family, variation and rate")
    recipient, counterpart = matches[0]
    return EffectPair(recipient.family, counterpart.variant)


def resolve_target_item(item: LibraryItem, model: str, profile: ModelProfile | None = None) -> LibraryItem:
    profile = get_profile(model) if profile is None else profile
    content = item.content
    projected = content
    if isinstance(content, MusicProfile) and content.model != model:
        source = get_profile(content.model)
        source_code = music_code_for(content.model, content.mode, profile=source)
        target_code = music_code_for(model, content.mode, profile=profile)
        source_variant = music_variant(source, source_code)
        target_variant = music_variant(profile, target_code)
        if content.mode.startswith("mode_") and source.music_grammar != profile.music_grammar:
            raise ValueError("Numbered music modes have no qualified cross-format identity")
        if content.zones is not None and (
            source.music_grammar != profile.music_grammar or source.native_zones != profile.native_zones
        ):
            raise ValueError("Music zones require equivalent source roles and geometry")
        if content.calm is None and (
            (source_variant.calm_default if source_variant else False)
            != (target_variant.calm_default if target_variant else False)
        ):
            raise ValueError("The target has a different default music style")
        if (
            content.palette is None
            and source_variant
            and target_variant
            and (source_variant.template != target_variant.template)
        ):
            raise ValueError("The target has different implicit music parameters")
        parameters = compile_music_parameters(content.parameters, source_code, source)
        target_parameters = compile_music_parameters(parameters, target_code, profile)
        if parameters != target_parameters:
            raise ValueError("The target introduces different implicit music parameters")
        projected = replace(content, model=model, parameters=parameters)
    elif isinstance(content, WorkshopEffect) and content.model != model:
        source = get_profile(content.model)
        different_format = (
            source.effect_grammar != profile.effect_grammar
            or source.workshop_brightness_algorithm != profile.workshop_brightness_algorithm
        )
        if different_format and any(
            layer.unknown_flags
            or layer.excess
            or layer.distribution.extensions
            or layer.selected_movement.unknown_flags
            or layer.overall_movement.unknown_flags
            for layer in content.effect.layers
        ):
            raise ValueError("Opaque Workshop fields cannot be transferred to a different format")
        projected = replace(content, model=model)
    elif isinstance(content, PaintedEffect) and content.model is not None and content.model != model:
        source = get_profile(content.model)
        if source.effect_grammar != profile.effect_grammar:
            raise ValueError("Paint requires an equivalent animation and addressing format")
        projected = replace(content, model=model)
    elif isinstance(content, VideoProfile) and content.model != model:
        if not profile.supports_video_mode:
            raise ValueError(f"{model} video-profile application is not supported")
        source = get_profile(content.model)
        if (
            source.video_grammar != profile.video_grammar
            or source.video_white_balance_calibration != profile.video_white_balance_calibration
            or source.video_brightness_zones != profile.video_brightness_zones
        ):
            raise ValueError("Video profiles require equivalent capture, calibration and zone contracts")
        projected = replace(content, model=model)
    elif isinstance(
        content, SingleEffect | MultiEffect | PaletteDiyEffect | H6179SingleDiyEffect | H6179MixedDiyEffect
    ):
        source_model = (
            content.model
            if isinstance(content, PaletteDiyEffect | H6179SingleDiyEffect | H6179MixedDiyEffect)
            else LEGACY_CATALOGUE_SKU
        )
        cross_format = (
            isinstance(content, SingleEffect | MultiEffect)
            and profile.effect_grammar in {"H6199", "H6179"}
            or isinstance(content, PaletteDiyEffect | H6179SingleDiyEffect | H6179MixedDiyEffect)
            and source_model != model
        )
        if cross_format:
            source_catalogue = MODEL_EFFECT_CATALOGUES.get(source_model)
            if source_catalogue is None:
                raise ValueError("The source effect catalogue is unavailable")
            target_catalogue = MODEL_EFFECT_CATALOGUES.get(model)
            if target_catalogue is None:
                raise ValueError("The target has no effect catalogue")
            pairs = (
                content.effects
                if isinstance(content, MultiEffect)
                else content.components
                if isinstance(content, H6179MixedDiyEffect)
                else (content,)
            )
            resolved = tuple(
                _target_pair(pair.family, pair.variant, source_catalogue, target_catalogue, profile) for pair in pairs
            )
            multi = isinstance(content, MultiEffect | H6179MixedDiyEffect)
            if profile.effect_grammar == "H6199":
                if multi:
                    raise ValueError("The target palette workflow does not support Multi")
                projected = PaletteDiyEffect(
                    model, resolved[0].family, resolved[0].variant, content.speed, content.palette
                )
            elif profile.effect_grammar == "H6179":
                projected = (
                    H6179MixedDiyEffect(model, resolved, content.speed, content.palette)
                    if multi
                    else H6179SingleDiyEffect(
                        model, resolved[0].family, resolved[0].variant, content.speed, content.palette
                    )
                )
            else:
                projected = (
                    MultiEffect(resolved, content.speed, content.palette)
                    if multi
                    else SingleEffect(resolved[0].family, resolved[0].variant, content.speed, content.palette)
                )
    return item if projected is content else replace(item, content=projected, content_hash="")
