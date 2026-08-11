"""Decode catalogue layered scenes into canonical, non-compilable values."""

from __future__ import annotations

import base64
from typing import Any

from .generated_protocol_adapter import SceneBody, parse_scene_body_param
from .layered_scene import (
    AppliedArea,
    BrightnessPattern,
    CatalogueRef,
    Distribution,
    EffectLayer,
    LayeredEffect,
    LayeredScene,
    Movement,
    Selection,
)
from .scenes import SceneEntry

__all__ = ["decode_catalogue_layered_scene", "decode_layered_scene"]


def decode_layered_scene(
    template: CatalogueRef,
    raw_param: bytes,
    *,
    speed_index: int | None = None,
) -> LayeredScene:
    """Decode a type-2 parameter without adding an application or compilation path."""
    parsed = parse_scene_body_param(raw_param)
    return LayeredScene(
        template=template,
        effect=LayeredEffect(tuple(_decode_layer(record.body) for record in parsed.records)),
        speed_index=speed_index,
        raw_param=raw_param,
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
