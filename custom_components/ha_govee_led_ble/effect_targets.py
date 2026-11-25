"""Resolve immutable authoring content against a recipient's declared contract."""

from dataclasses import replace

from .const import ModelProfile, get_profile
from .effect_catalogue import MODEL_EFFECT_CATALOGUES
from .effect_catalogue_models import ModelEffectCatalogue
from .effect_content_ids import (
    MULTI_EFFECT_CONTENT_KIND,
    SINGLE_EFFECT_CONTENT_KIND,
    TYPED_MIXED_DIY_CONTENT_KIND,
    TYPED_SINGLE_DIY_CONTENT_KIND,
)
from .effect_contracts import (
    ContentProjection,
    release_content_capability,
    release_content_reference_model,
    release_projection_capability,
)
from .effect_domain import (
    EffectPair,
    LibraryItem,
    MultiEffect,
    MusicProfile,
    PaintedEffect,
    PaletteDiyEffect,
    RetainedSceneEffect,
    SingleEffect,
    TypedMixedDiyEffect,
    TypedSingleDiyEffect,
    VideoProfile,
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
    elif isinstance(content, RetainedSceneEffect) and content.model != model:
        source = get_profile(content.model)
        different_format = (
            source.effect_grammar != profile.effect_grammar
            or source.workshop_brightness_algorithm != profile.workshop_brightness_algorithm
        )
        if content.application != "workshop" or content.carrier != "rgbic_v1":
            raise ValueError("Retained Workshop carrier is bound to its source model")
        if content.effect is None:
            raise ValueError("Workshop has no transferable layered content")
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
        content, SingleEffect | MultiEffect | PaletteDiyEffect | TypedSingleDiyEffect | TypedMixedDiyEffect
    ):
        source_content_kind = (
            SINGLE_EFFECT_CONTENT_KIND
            if isinstance(content, SingleEffect)
            else MULTI_EFFECT_CONTENT_KIND
            if isinstance(content, MultiEffect)
            else TYPED_SINGLE_DIY_CONTENT_KIND
            if isinstance(content, TypedSingleDiyEffect)
            else TYPED_MIXED_DIY_CONTENT_KIND
            if isinstance(content, TypedMixedDiyEffect)
            else "palette_diy"
        )
        source_model = (
            content.model
            if isinstance(content, PaletteDiyEffect | TypedSingleDiyEffect | TypedMixedDiyEffect)
            else release_content_reference_model(source_content_kind)
        )
        projection = (
            release_content_capability(model, source_content_kind)
            if source_model == model
            else release_projection_capability(model, source_content_kind)
        )
        cross_format = projection is not None and (
            projection.persistent_content_kind != source_content_kind
            or isinstance(content, PaletteDiyEffect | TypedSingleDiyEffect | TypedMixedDiyEffect)
            and source_model != model
        )
        if cross_format and projection is not None:
            if source_model is None:
                raise ValueError("The source effect has no declared catalogue identity")
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
                if isinstance(content, TypedMixedDiyEffect)
                else (content,)
            )
            resolved = tuple(
                _target_pair(pair.family, pair.variant, source_catalogue, target_catalogue, profile) for pair in pairs
            )
            multi = isinstance(content, MultiEffect | TypedMixedDiyEffect)
            if projection.content_projection is ContentProjection.PALETTE_DIY:
                if multi:
                    raise ValueError("The target palette workflow does not support Multi")
                projected = PaletteDiyEffect(
                    model, resolved[0].family, resolved[0].variant, content.speed, content.palette
                )
            elif projection.content_projection is ContentProjection.TYPED_DIY:
                projected = (
                    TypedMixedDiyEffect(model, resolved, content.speed, content.palette)
                    if multi
                    else TypedSingleDiyEffect(
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
