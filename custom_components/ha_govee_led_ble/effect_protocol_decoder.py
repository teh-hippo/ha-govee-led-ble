"""Decode generated outbound effect trees into canonical effect content."""

from __future__ import annotations

from typing import Any

from .effect_catalogue import (
    H617A_PAINTED_EFFECTS,
    H617A_TYPE04_FAMILIES,
    H6199_DIY_EFFECTS,
)
from .effect_domain import (
    H617A_SEGMENT_COUNT,
    EffectContent,
    EffectPair,
    MultiEffect,
    PaintedEffect,
    PaletteDiyEffect,
    SingleEffect,
)
from .generated_protocol_adapter import (
    DiyType03,
    DiyType04,
    H6199EffectUpload,
    SceneBody,
    SceneType1Body,
    parse_a3_effect_envelope,
)
from .layered_scene_decoder import decode_workshop_effect
from .transport import reassemble_a3

__all__ = [
    "UnsupportedA3EffectError",
    "decode_a3_effect",
    "decode_a3_effect_frames",
]


class UnsupportedA3EffectError(ValueError):
    """An A3 tree cannot be represented by a supported canonical effect type."""


def decode_a3_effect_frames(
    frames: tuple[bytes, ...],
    model: str,
) -> EffectContent:
    """Reassemble and decode locally generated A3 frames through Kaitai."""
    envelope = reassemble_a3(frames)
    return decode_a3_effect(parse_a3_effect_envelope(envelope, model), model)


def decode_a3_effect(tree: Any, model: str) -> EffectContent:
    """Decode a parsed generated A3 tree without assigning unevidenced semantics."""
    if model == "H617A":
        if isinstance(tree, DiyType03):
            return _decode_h617a_painted(tree)
        if isinstance(tree, DiyType04):
            return _decode_h617a_type04(tree)
        if isinstance(tree, SceneBody):
            return _decode_layered_tree(tree, model)
        if isinstance(tree, SceneType1Body):
            raise UnsupportedA3EffectError(
                "H617A type-1 scene bodies require catalogue identity and are not decoded from upload packets alone"
            )
        raise TypeError("tree is not a generated H617A A3 effect root")

    if model == "H6199":
        if not isinstance(tree, H6199EffectUpload):
            raise TypeError("tree is not a generated H6199 A3 effect root")
        if tree.kind == H6199EffectUpload.BodyKind.diy:
            return _decode_h6199_palette_diy(tree)
        if tree.kind == H6199EffectUpload.BodyKind.scene:
            return _decode_layered_tree(tree, model)
        if tree.kind == H6199EffectUpload.BodyKind.builtin_parameters:
            raise UnsupportedA3EffectError(
                "H6199 built-in parameter bodies require catalogue identity and are not "
                "decoded from upload packets alone"
            )
        raise UnsupportedA3EffectError(f"H6199 A3 body kind {int(tree.kind)} is not supported")

    raise ValueError(f"{model} has no canonical A3 effect decoder")


def _decode_h617a_painted(tree: Any) -> PaintedEffect:
    effect = getattr(tree.effect, "name", None)
    supported = {entry["id"] for entry in H617A_PAINTED_EFFECTS}
    if not isinstance(effect, str) or effect not in supported:
        raise UnsupportedA3EffectError(f"H617A painted effect {int(tree.effect)} is not catalogued")
    if _rgb(tree.background) != (0, 0, 0):
        raise UnsupportedA3EffectError("H617A painted background cannot be represented by canonical PaintedEffect")
    if tree.num_groups != len(tree.groups):
        raise UnsupportedA3EffectError("H617A painted group count does not match its generated tree")
    _require_zero_padding(tree.padding, "H617A painted")

    segments: list[tuple[int, int, int] | None] = [None] * H617A_SEGMENT_COUNT
    for group in tree.groups:
        if group.num_segment_indices != len(group.segment_indices) or not group.segment_indices:
            raise UnsupportedA3EffectError("H617A painted groups must contain their declared segments")
        fill = _rgb(group.fill)
        for index in group.segment_indices:
            if not 0 <= index < H617A_SEGMENT_COUNT:
                raise UnsupportedA3EffectError(f"H617A painted segment {index} is out of range")
            if segments[index] is not None:
                raise UnsupportedA3EffectError(f"H617A painted segment {index} appears more than once")
            segments[index] = fill

    return PaintedEffect(
        effect=effect,
        speed=tree.speed,
        brightness=tree.brightness,
        segments=tuple(segments),
    )


def _decode_h617a_type04(tree: Any) -> SingleEffect | MultiEffect:
    body = tree.body
    _require_zero_padding(body.padding, "H617A type-04")
    palette = tuple(_rgb(colour) for colour in body.palette.colours)
    if body.len_palette != len(palette) * 3:
        raise UnsupportedA3EffectError("H617A type-04 palette length does not match its generated tree")

    if tree.family != 0xFF:
        _require_h617a_effect(tree.family, body.variant, multi=False)
        return SingleEffect(
            family=tree.family,
            variant=body.variant,
            speed=body.speed,
            palette=palette,
        )

    if body.variant != 0:
        raise UnsupportedA3EffectError(f"H617A Multi reserved variant must be 0, received {body.variant}")
    if body.seqlen != len(body.pairs) * 2:
        raise UnsupportedA3EffectError("H617A Multi sequence length does not match its generated tree")
    effects = tuple(EffectPair(pair.family, pair.variant) for pair in body.pairs)
    for effect in effects:
        _require_h617a_effect(effect.family, effect.variant, multi=True)
    return MultiEffect(effects=effects, speed=body.speed, palette=palette)


def _decode_h6199_palette_diy(tree: Any) -> PaletteDiyEffect:
    if tree.chunk_count != tree.diy_chunk_count:
        raise UnsupportedA3EffectError(
            f"H6199 palette DIY requires {tree.diy_chunk_count} chunks, received {tree.chunk_count}"
        )
    content = tree.content
    family = int(content.family)
    supported = {(effect.family, effect.variant) for effect in H6199_DIY_EFFECTS}
    if (family, content.variant) not in supported:
        raise UnsupportedA3EffectError(
            f"H6199 palette DIY family {family} variation {content.variant} is not catalogued"
        )
    if content.palette_len != len(content.palette) * 3:
        raise UnsupportedA3EffectError("H6199 palette DIY length does not match its generated tree")
    _require_zero_padding(content.padding, "H6199 palette DIY")
    return PaletteDiyEffect(
        model="H6199",
        family=family,
        variant=content.variant,
        speed=content.speed,
        palette=tuple(_rgb(colour) for colour in content.palette),
    )


def _decode_layered_tree(tree: Any, model: str) -> EffectContent:
    envelope = bytes(tree._io.to_byte_array())
    effect, _trailing_padding = decode_workshop_effect(model, envelope[3:])
    return effect


def _require_h617a_effect(family: int, variant: int, *, multi: bool) -> None:
    for entry in H617A_TYPE04_FAMILIES:
        if entry.family != family:
            continue
        if not any(variation.variant == variant for variation in entry.variations):
            break
        if multi and not entry.supports_multi:
            raise UnsupportedA3EffectError(f"H617A family {family} variation {variant} is not catalogued for Multi")
        return
    raise UnsupportedA3EffectError(f"H617A family {family} variation {variant} is not catalogued")


def _require_zero_padding(padding: list[int], context: str) -> None:
    if any(padding):
        raise UnsupportedA3EffectError(f"{context} contains non-zero reserved padding")


def _rgb(colour: Any) -> tuple[int, int, int]:
    return int(colour.red), int(colour.green), int(colour.blue)
