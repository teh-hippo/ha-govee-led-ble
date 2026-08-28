"""Decode and encode catalogue layered scenes as canonical values."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from .generated_protocol_adapter import (
    GoveeShared,
    H6199EffectUpload,
    SceneBody,
    SceneParameterTooLargeError,
    WorkshopBody,
    new_child,
    new_rgb,
    parse_h6199_workshop_content,
    parse_scene_body,
    parse_workshop_body,
    serialize_h6199_workshop_content,
    serialize_scene_body_param,
    serialize_workshop_body_param,
)
from .layered_scene import (
    _LAYER_UNKNOWN_FLAGS_MASK,
    _MOVEMENT_UNKNOWN_FLAGS_MASK,
    AppliedArea,
    BrightnessPattern,
    CatalogueRef,
    Distribution,
    EffectLayer,
    LayeredEffect,
    LayeredScene,
    LayeredSceneValidationError,
    Movement,
    Selection,
)
from .scenes import SceneEntry

__all__ = [
    "decode_catalogue_layered_scene",
    "decode_layered_scene",
    "decode_workshop_effect",
    "encode_layered_scene",
    "encode_workshop_effect",
]

_APPLIED_AREA_WIDTH_SHIFT = 4
_LAYER_FLAG_BRIGHTNESS_GRADIENT = 0x02
_DIRECTION_BACKWARD_BIT = 0x80
_DIRECTION_METHOD_MASK = 0x7F
_MOVEMENT_ENABLED_BIT = 0x10
_MOVEMENT_ENTER_EXIT_BIT = 0x04
_MOVEMENT_DIRECTION_MASK = 0x03


def decode_layered_scene(
    template: CatalogueRef,
    raw_param: bytes,
    *,
    speed_index: int | None = None,
) -> LayeredScene:
    """Decode a type-2 parameter while preserving source-only bytes."""
    parsed, trailing_padding = parse_scene_body(raw_param)
    return LayeredScene(
        template=template,
        effect=LayeredEffect(tuple(_decode_layer(record.body) for record in parsed.records)),
        speed_index=speed_index,
        raw_param=raw_param,
        trailing_padding=trailing_padding,
    )


def decode_catalogue_layered_scene(sku: str, entry: SceneEntry) -> LayeredScene | None:
    """Decode one type-2 catalogue entry, returning None for other scene grammars."""
    if entry.scene_type != int(SceneBody.SceneType.scene_v2):
        return None
    if not entry.param:
        raise ValueError("type-2 catalogue scene has no parameter")
    return decode_layered_scene(
        CatalogueRef(sku=sku, scene_id=entry.scene_id, effect_id=entry.effect_id),
        base64.b64decode(entry.param, validate=True),
        speed_index=entry.speed.default_index if entry.speed is not None else None,
    )


def encode_layered_scene(scene: LayeredScene) -> bytes:
    """Serialize a canonical layered scene back to its type-2 parameter bytes."""
    root = SceneBody()
    root.scene_type = SceneBody.SceneType.scene_v2
    layers = scene.effect.layers
    root.num_records = len(layers)
    root.records = [_encode_record(SceneBody.Record, root, layer) for layer in layers]
    root.padding = [0] * scene.trailing_padding
    try:
        return serialize_scene_body_param(root)
    except SceneParameterTooLargeError as error:
        raise LayeredSceneValidationError(str(error)) from error


def decode_workshop_effect(
    model: str,
    raw_param: bytes,
) -> tuple[LayeredEffect, int]:
    """Decode a Workshop parameter through its model-specific generated structure."""
    if model == "H617A":
        parsed, trailing_padding = parse_workshop_body(raw_param)
        records = parsed.layers
    elif model == "H6199":
        parsed, trailing_padding = parse_h6199_workshop_content(raw_param)
        records = parsed.blocks
    else:
        raise ValueError(f"{model} has no Workshop grammar")
    return LayeredEffect(tuple(_decode_layer(record.body) for record in records)), trailing_padding


def encode_workshop_effect(
    model: str,
    effect: LayeredEffect,
    *,
    trailing_padding: int = 0,
) -> bytes:
    """Serialize Workshop layers through the model-specific generated structure."""
    serializer: Callable[[Any], bytes]
    if model == "H617A":
        root = WorkshopBody()
        root.a3_type = b"\x02"
        root.num_layers = len(effect.layers)
        root.layers = [_encode_record(WorkshopBody.LayerRecord, root, layer) for layer in effect.layers]
        root.padding = [0] * trailing_padding
        serializer = serialize_workshop_body_param
        value = root
    elif model == "H6199":
        root = H6199EffectUpload()
        content = new_child(H6199EffectUpload.SceneContent, root)
        content.num_blocks = len(effect.layers)
        content.blocks = [_encode_record(H6199EffectUpload.Block, content, layer) for layer in effect.layers]
        content.padding = [0] * trailing_padding
        serializer = serialize_h6199_workshop_content
        value = content
    else:
        raise ValueError(f"{model} has no Workshop grammar")
    try:
        return serializer(value)
    except SceneParameterTooLargeError as error:
        raise LayeredSceneValidationError(str(error)) from error


def _encode_record(record_type: Any, parent: Any, layer: EffectLayer) -> Any:
    record = new_child(record_type, parent)
    record.body = _encode_layer(record, layer)
    return record


def _encode_layer(record: Any, layer: EffectLayer) -> Any:
    body = new_child(GoveeShared.EffectLayer, record)
    body.applied_area = (layer.area.width_tenths << _APPLIED_AREA_WIDTH_SHIFT) | (layer.area.start_tenths & 0x0F)
    body.select_type = layer.selection.type
    body.select_param_1 = layer.selection.param_1
    body.select_param_2 = layer.selection.param_2
    body.layer_flags = (_LAYER_FLAG_BRIGHTNESS_GRADIENT if layer.brightness_gradient else 0) | (
        layer.unknown_flags & _LAYER_UNKNOWN_FLAGS_MASK
    )
    body.num_brightness_blocks = len(layer.brightness_patterns)
    body.brightness_blocks = [_encode_brightness_block(body, pattern) for pattern in layer.brightness_patterns]
    body.direction_distribution = (_DIRECTION_BACKWARD_BIT if layer.distribution.backwards else 0) | (
        layer.distribution.method & _DIRECTION_METHOD_MASK
    )
    body.colour_speed = layer.colour_speed
    body.colour_retention = layer.colour_retention
    body.num_palette = len(layer.palette)
    body.palette = [new_rgb(body, colour) for colour in layer.palette]
    body.selected_area_movement = _encode_movement(body, layer.selected_movement)
    body.overall_movement = _encode_movement(body, layer.overall_movement)
    body.priority = layer.priority
    body.excess = layer.excess
    return body


def _encode_brightness_block(body: Any, pattern: BrightnessPattern) -> Any:
    block = new_child(GoveeShared.BrightnessBlock, body)
    block.brightness_scope_start = pattern.scope_high
    block.brightness_scope_end = pattern.scope_low
    block.brightness_order = pattern.order
    block.brightness_speed = pattern.change_speed
    block.brightest_retention = pattern.brightest_retention
    block.darkest_retention = pattern.darkest_retention
    return block


def _encode_movement(body: Any, movement: Movement) -> Any:
    node = new_child(GoveeShared.Movement, body)
    node.packed = (
        (_MOVEMENT_ENABLED_BIT if movement.enabled else 0)
        | (_MOVEMENT_ENTER_EXIT_BIT if movement.enter_exit else 0)
        | (movement.direction & _MOVEMENT_DIRECTION_MASK)
        | (movement.unknown_flags & _MOVEMENT_UNKNOWN_FLAGS_MASK)
    )
    node.interval = movement.distance
    node.speed = movement.speed
    return node


def _decode_layer(layer: Any) -> EffectLayer:
    return EffectLayer(
        area=AppliedArea(
            start_tenths=int(layer.applied_area_start_tenths),
            width_tenths=int(layer.applied_area_width_tenths),
        ),
        selection=Selection(
            type=int(layer.select_type),
            param_1=int(layer.select_param_1),
            param_2=int(layer.select_param_2),
        ),
        brightness_gradient=bool(layer.brightness_is_gradient),
        brightness_patterns=tuple(
            BrightnessPattern(
                scope_high=int(block.scope_high),
                scope_low=int(block.scope_low),
                order=int(block.order),
                change_speed=int(block.change_speed),
                brightest_retention=int(block.retention_brightest),
                darkest_retention=int(block.retention_darkest),
            )
            for block in layer.brightness_blocks
        ),
        distribution=Distribution(
            method=int(layer.distribution_method),
            backwards=bool(layer.direction_is_backward),
        ),
        colour_speed=int(layer.colour_speed),
        colour_retention=int(layer.colour_retention),
        palette=tuple((int(colour.r), int(colour.g), int(colour.b)) for colour in layer.palette),
        selected_movement=_decode_movement(layer.selected_area_movement),
        overall_movement=_decode_movement(layer.overall_movement),
        priority=int(layer.priority),
        unknown_flags=int(layer.unknown_flags),
        excess=bytes(layer.excess),
    )


def _decode_movement(movement: Any) -> Movement:
    return Movement(
        enabled=bool(movement.enabled),
        enter_exit=bool(movement.enter_exit_effect),
        direction=int(movement.direction),
        distance=int(movement.interval),
        speed=int(movement.speed),
        unknown_flags=int(movement.unknown_flags),
    )
