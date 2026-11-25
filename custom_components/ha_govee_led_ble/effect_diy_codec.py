"""Codec-owned preparation for generic DIY effect content."""

from dataclasses import dataclass

from .const import ModelProfile
from .effect_catalogue import (
    H617A_TYPE04_APPLY_CODE,
    H617A_WORKSHOP_APPLY_CODE,
    H617A_WORKSHOP_SCENE_TYPE,
    H6099_DIY_APPLY_CODE,
    H6199_WORKSHOP_APPLY_CODE,
    H6199_WORKSHOP_APPLY_MUSIC_CODE,
)
from .effect_commands import (
    DiyPaintGroup,
    build_h617a_diy_multi,
    build_h617a_diy_painted,
    build_h617a_diy_single,
    build_h6199_palette_diy,
)
from .effect_content_ids import (
    MULTI_EFFECT_CONTENT_KIND,
    PAINTED_EFFECT_CONTENT_KIND,
    SINGLE_EFFECT_CONTENT_KIND,
    TYPED_MIXED_DIY_CONTENT_KIND,
    TYPED_SINGLE_DIY_CONTENT_KIND,
)
from .effect_domain import (
    EffectContent,
    MultiEffect,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
    TypedMixedDiyEffect,
    TypedSingleDiyEffect,
)
from .generated_protocol_adapter import build_diy_activation, build_scene_activation
from .protocol_core import H6199EffectUpload, SceneBody
from .protocol_effect_bodies import build_dedicated_diy, build_inline_diy

GenericDiyContent = PaintedEffect | SingleEffect | MultiEffect
TypedDiyContent = TypedSingleDiyEffect | TypedMixedDiyEffect


@dataclass(frozen=True, slots=True)
class GenericDiyPreparation:
    content_kind: str
    upload_packets: tuple[bytes, ...]
    activation_packet: bytes
    upload_transport: str
    upload_subtype: int | None
    upload_prefix: int | None


def generic_diy_content_kind(content: EffectContent) -> str:
    if isinstance(content, PaintedEffect):
        return PAINTED_EFFECT_CONTENT_KIND
    if isinstance(content, SingleEffect):
        return SINGLE_EFFECT_CONTENT_KIND
    if isinstance(content, MultiEffect):
        return MULTI_EFFECT_CONTENT_KIND
    raise ValueError("unsupported generic DIY effect content")


def is_single_or_multi_diy_kind(content_kind: str) -> bool:
    return content_kind in {SINGLE_EFFECT_CONTENT_KIND, MULTI_EFFECT_CONTENT_KIND}


def typed_diy_content_kind(content: TypedDiyContent) -> str:
    return TYPED_SINGLE_DIY_CONTENT_KIND if isinstance(content, TypedSingleDiyEffect) else TYPED_MIXED_DIY_CONTENT_KIND


def prepare_typed_diy(
    content: TypedDiyContent,
    diy_code: int,
    model: str,
    profile: ModelProfile,
) -> GenericDiyPreparation:
    if profile.effect_grammar != "H6179":
        raise ValueError(f"{model} has no selected typed DIY codec")
    from .effect_commands import build_h6179_diy

    transport = profile.diy_upload_transport
    return GenericDiyPreparation(
        content_kind=typed_diy_content_kind(content),
        upload_packets=tuple(build_h6179_diy(content, profile=profile)),
        activation_packet=build_diy_activation(diy_code, model, profile=profile),
        upload_transport="a3" if transport == "a3" else "a1_02",
        upload_subtype=4 if transport == "a3" else None,
        upload_prefix=None,
    )


def prepare_palette_diy(
    content: PaletteDiyEffect,
    diy_code: int,
    model: str,
    profile: ModelProfile,
) -> GenericDiyPreparation:
    if profile.effect_grammar != "H6199":
        raise ValueError(f"{model} has no selected palette DIY codec")
    upload_packets = build_h6199_palette_diy(
        content.family,
        content.variant,
        content.speed,
        content.palette,
    )
    return GenericDiyPreparation(
        content_kind="palette_diy",
        upload_packets=tuple(upload_packets),
        activation_packet=build_diy_activation(diy_code, model, profile=profile),
        upload_transport="a3",
        upload_subtype=int(H6199EffectUpload.BodyKind.diy),
        upload_prefix=None,
    )


def default_generic_diy_selector(content: GenericDiyContent, profile: ModelProfile) -> int:
    if profile.effect_grammar_has("default_diy_selector_254"):
        return H6099_DIY_APPLY_CODE
    if not isinstance(content, PaintedEffect) and profile.a1_diy_selector is not None:
        return profile.a1_diy_selector
    if isinstance(content, PaintedEffect):
        return 800
    return H617A_TYPE04_APPLY_CODE


def prepare_generic_diy(
    content: GenericDiyContent,
    diy_code: int,
    model: str,
    profile: ModelProfile,
) -> GenericDiyPreparation:
    upload_prefix = profile.a1_diy_prefix if profile.a1_diy_prefix is not None else profile.a1_diy_selector
    if profile.effect_grammar_has("dedicated_a1_diy") and isinstance(content, SingleEffect | MultiEffect):
        upload_packets = build_dedicated_diy(content, diy_code, profile)
    elif isinstance(content, PaintedEffect):
        upload_packets = build_h617a_diy_painted(
            content.effect,
            content.speed,
            content.brightness,
            content.background,
            _paint_groups(content.segments),
            segment_count=len(content.segments),
            grammar=profile.effect_grammar or "",
        )
    elif isinstance(content, SingleEffect):
        upload_packets = (
            []
            if profile.diy_upload_transport == "single"
            else build_h617a_diy_single(
                content.family,
                content.variant,
                content.speed,
                content.palette,
                a1_selector=upload_prefix,
            )
        )
    elif isinstance(content, MultiEffect):
        upload_packets = build_h617a_diy_multi(
            tuple((effect.family, effect.variant) for effect in content.effects),
            content.speed,
            content.palette,
            a1_selector=upload_prefix,
        )
    else:
        raise ValueError("unsupported generic DIY effect content")

    transport = profile.diy_upload_transport or (
        "a1_02" if profile.a1_diy_selector is not None and isinstance(content, SingleEffect | MultiEffect) else "a3"
    )
    subtype = (
        None
        if profile.diy_upload_transport in {"a1_02", "single"}
        else 3
        if isinstance(content, PaintedEffect)
        else 4
        if profile.a1_diy_selector is None
        else None
    )
    return GenericDiyPreparation(
        content_kind=generic_diy_content_kind(content),
        upload_packets=tuple(upload_packets),
        activation_packet=generic_diy_activation_packet(content, diy_code, model, profile),
        upload_transport=transport,
        upload_subtype=subtype,
        upload_prefix=profile.a1_diy_prefix,
    )


def generic_diy_activation_packet(
    content: GenericDiyContent,
    diy_code: int,
    model: str,
    profile: ModelProfile,
) -> bytes:
    if profile.diy_upload_transport == "single" and isinstance(content, SingleEffect):
        return build_inline_diy(diy_code, content.family, content.variant, content.speed, content.palette)
    return build_diy_activation(diy_code, model, profile=profile)


def default_workshop_upload(profile: ModelProfile) -> tuple[int, int]:
    subtype = (
        int(H6199EffectUpload.BodyKind.scene)
        if profile.effect_grammar_has("display_scene_body")
        else int(SceneBody.SceneType.scene_v2)
    )
    if profile.workshop_scene_selector is not None:
        return subtype, profile.workshop_scene_selector
    return subtype, (
        H617A_WORKSHOP_APPLY_CODE
        if profile.effect_grammar_has("h617a_workshop_selector")
        else H6199_WORKSHOP_APPLY_CODE
    )


def retained_scene_activation_packet(
    model: str,
    selector: int,
    application: str,
    profile: ModelProfile,
) -> bytes:
    scene_type = (
        H617A_WORKSHOP_SCENE_TYPE
        if application == "workshop"
        and profile.workshop_scene_selector is None
        and profile.command_grammar_has("workshop_scene_type")
        else 0
    )
    return build_scene_activation(
        model,
        selector,
        H6199_WORKSHOP_APPLY_MUSIC_CODE,
        scene_type=scene_type,
        profile=profile,
    )


def _paint_groups(segments: tuple[tuple[int, int, int] | None, ...]) -> tuple[DiyPaintGroup, ...]:
    grouped: dict[tuple[int, int, int], list[int]] = {}
    for index, colour in enumerate(segments):
        if colour is not None:
            grouped.setdefault(colour, []).append(index)
    return tuple(
        DiyPaintGroup(colour, tuple(indices))
        for colour, indices in sorted(grouped.items(), key=lambda item: item[1][0])
    )
