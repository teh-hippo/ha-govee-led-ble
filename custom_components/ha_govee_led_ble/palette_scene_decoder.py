"""Decode and encode catalogue palette scenes as canonical values."""

from __future__ import annotations

import base64
from typing import Any, cast

from .effect_domain import (
    PALETTE_CONFIG_RESERVED_MASK,
    CatalogueRef,
    EffectValidationError,
    PaletteScene,
    SceneStep,
)
from .generated_protocol_adapter import parse_scene_type1_body, serialize_scene_type1_body_param
from .protocol_core import GoveeShared, SceneParameterTooLargeError, SceneType1Body, new_child, new_rgb
from .scenes import SceneEntry

__all__ = [
    "decode_catalogue_palette_scene",
    "decode_palette_scene",
    "encode_palette_scene",
]

_CONFIG_BRIGHTNESS_BIT = 0x80
_CONFIG_LAYOUT_SHIFT = 4
_CONFIG_COLOUR_STRIDE = 3
_CONFIG_INLINE_EXTRA_STRIDE = 5


def decode_palette_scene(
    template: CatalogueRef,
    raw_param: bytes,
    *,
    speed_index: int | None = None,
) -> PaletteScene:
    """Decode a type-1 parameter into its lossless authored representation."""
    parsed, trailing_padding = parse_scene_type1_body(raw_param)
    layout = int(parsed.layout)
    colour_stride = int(parsed.colour_stride)
    return PaletteScene(
        template=template,
        layout=layout,
        brightness_flag=bool(parsed.brightness_flag),
        steps=tuple(_decode_step(step, layout, colour_stride) for step in parsed.steps),
        palette=(tuple(_decode_colour(colour) for colour in parsed.palette) if layout == 0 else ()),
        speed_index=speed_index,
        config_flags=int(parsed.config) & PALETTE_CONFIG_RESERVED_MASK,
        trailing_padding=trailing_padding,
    )


def decode_catalogue_palette_scene(sku: str, entry: SceneEntry) -> PaletteScene | None:
    """Decode one type-1 catalogue entry, returning None for other scene grammars."""
    if entry.scene_type != 1:
        return None
    if not entry.param:
        raise ValueError("type-1 catalogue scene has no parameter")
    return decode_palette_scene(
        CatalogueRef(sku=sku, scene_id=entry.scene_id, effect_id=entry.effect_id),
        base64.b64decode(entry.param, validate=True),
        speed_index=entry.speed.default_index if entry.speed is not None else None,
    )


def encode_palette_scene(scene: PaletteScene) -> bytes:
    """Serialize a canonical palette scene back to its type-1 parameter bytes."""
    root = SceneType1Body()
    root.scene_type = 1
    content = new_child(GoveeShared.SceneType1Content, root)
    colour_stride = (
        _CONFIG_INLINE_EXTRA_STRIDE
        if scene.layout == 1 and scene.steps and scene.steps[0].inline_extra is not None
        else _CONFIG_COLOUR_STRIDE
    )
    content.config = (
        (_CONFIG_BRIGHTNESS_BIT if scene.brightness_flag else 0)
        | (scene.layout << _CONFIG_LAYOUT_SHIFT)
        | (scene.config_flags & PALETTE_CONFIG_RESERVED_MASK)
        | colour_stride
    )
    content.num_steps = len(scene.steps)
    content.steps = [_encode_step(content, step, scene.layout) for step in scene.steps]
    if scene.layout == 0:
        content.num_palette = len(scene.palette)
        content.palette = [new_rgb(content, colour) for colour in scene.palette]
    content.padding = [0] * scene.trailing_padding
    root.content = content
    try:
        return serialize_scene_type1_body_param(root)
    except SceneParameterTooLargeError as error:
        raise EffectValidationError(str(error)) from error


def _decode_step(step: Any, layout: int, colour_stride: int = _CONFIG_COLOUR_STRIDE) -> SceneStep:
    if layout == 0:
        return SceneStep(
            value=int(step.value),
            colour=_decode_colour(step.colour),
        )
    return SceneStep(
        value=int(step.param.value),
        colour=_decode_colour(step.param.colour),
        inline_colour=_decode_colour(step.colour),
        inline_extra=int(step.unknown_extra) if colour_stride == _CONFIG_INLINE_EXTRA_STRIDE else None,
    )


def _encode_step(parent: Any, step: SceneStep, layout: int) -> Any:
    if layout == 0:
        node = new_child(GoveeShared.SceneType1Step, parent)
        node.colour = new_rgb(node, step.colour)
        node.value = step.value
        return node
    inline = new_child(GoveeShared.SceneType1StepInlineColour, parent)
    param = new_child(GoveeShared.SceneType1Step, inline)
    param.colour = new_rgb(param, step.colour)
    param.value = step.value
    inline.param = param
    inline.colour = new_rgb(inline, cast(tuple[int, int, int], step.inline_colour))
    if step.inline_extra is not None:
        inline.unknown_extra = step.inline_extra
    return inline


def _decode_colour(colour: Any) -> tuple[int, int, int]:
    return int(colour.r), int(colour.g), int(colour.b)
