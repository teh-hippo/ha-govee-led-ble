"""Semantic transforms for H7025's native 0x58 DIY body."""

from __future__ import annotations

from typing import Any

from kaitaistruct import KaitaiStructError

from .native_effect import NativeDiyLayer, NativeEffect
from .protocol_core import H7025DiyBody, new_child, new_rgb, serialize_native_body

H7025_NATIVE_DIY_FAMILY = 767

_PRESETS = {
    16: (int(H7025DiyBody.SubEffect.retrace), 0),
    17: (int(H7025DiyBody.SubEffect.spray), 1),
    18: (int(H7025DiyBody.SubEffect.spray), 2),
    19: (int(H7025DiyBody.SubEffect.streamer), 0),
    20: (int(H7025DiyBody.SubEffect.streamer), 1),
    21: (int(H7025DiyBody.SubEffect.glimmer), 0),
    22: (int(H7025DiyBody.SubEffect.star_flash), 0),
    23: (int(H7025DiyBody.SubEffect.pile_up), 0),
    24: (int(H7025DiyBody.SubEffect.pile_up), 1),
}

_PALETTE_MINIMUMS = {20: 2, 24: 2}


def _rgb(value: Any) -> tuple[int, int, int]:
    return int(value.red), int(value.green), int(value.blue)


def validate_h7025_diy(content: NativeEffect) -> None:
    content.__post_init__()
    if content.model != "H7025" or content.family != H7025_NATIVE_DIY_FAMILY or content.preset_id not in _PRESETS:
        raise ValueError("H7025 native DIY requires an exact catalogue preset")
    if len(content.layers) != 1 or not isinstance(content.layers[0], NativeDiyLayer):
        raise ValueError("H7025 native DIY requires one semantic layer")
    layer = content.layers[0]
    kind, variant = _PRESETS[content.preset_id]
    if layer.kind != kind or not layer.enabled or layer.parameters or layer.direction or layer.angle or layer.opaque:
        raise ValueError("H7025 native DIY sub-effect does not match its template")
    palette_minimum = _PALETTE_MINIMUMS.get(content.preset_id, 1)
    if not palette_minimum <= len(layer.palette) <= 8:
        raise ValueError(f"H7025 native DIY palette must contain {palette_minimum} to 8 colours")
    if not 0 <= layer.speed <= 100:
        raise ValueError("H7025 native DIY speed is outside the supported range")
    if kind == H7025DiyBody.SubEffect.retrace:
        valid = 1 <= layer.parameter <= 10 and not layer.points and not layer.flag and not layer.secondary_palette
    elif kind == H7025DiyBody.SubEffect.spray:
        valid = (
            layer.parameter == variant
            and bool(layer.points)
            and len(layer.points) == 2
            and 1 <= layer.points[0] <= 5
            and 2 <= layer.points[1] <= 5
            and not layer.flag
            and not layer.secondary_palette
        )
    elif kind == H7025DiyBody.SubEffect.glimmer:
        valid = 0 <= layer.parameter <= 2 and not layer.points and not layer.flag and not layer.secondary_palette
    elif kind == H7025DiyBody.SubEffect.star_flash:
        valid = layer.parameter == 3 and not layer.points and not layer.flag and len(layer.secondary_palette) == 1
    else:
        valid = 1 <= layer.parameter <= 2 and layer.flag == variant and not layer.points and not layer.secondary_palette
    if not valid:
        raise ValueError("H7025 native DIY parameters are outside the exact template contract")


def _palette(parent: Any, colours: tuple[tuple[int, int, int], ...]) -> Any:
    value = new_child(H7025DiyBody.Palette, parent)
    value.count = len(colours)
    value.colours = [new_rgb(value, colour) for colour in colours]
    return value


def encode_h7025_diy(content: NativeEffect) -> bytes:
    validate_h7025_diy(content)
    layer = content.layers[0]
    assert isinstance(layer, NativeDiyLayer)
    body = new_child(H7025DiyBody.Body, H7025DiyBody())
    body.sub_effect = layer.kind
    tail_type = {
        int(H7025DiyBody.SubEffect.retrace): H7025DiyBody.Retrace,
        int(H7025DiyBody.SubEffect.spray): H7025DiyBody.Spray,
        int(H7025DiyBody.SubEffect.streamer): H7025DiyBody.Streamer,
        int(H7025DiyBody.SubEffect.glimmer): H7025DiyBody.Glimmer,
        int(H7025DiyBody.SubEffect.star_flash): H7025DiyBody.StarFlash,
        int(H7025DiyBody.SubEffect.pile_up): H7025DiyBody.PileUp,
    }[layer.kind]
    tail = new_child(tail_type, body)
    tail.speed = layer.speed
    tail.palette = _palette(tail, layer.palette)
    if tail_type is H7025DiyBody.Retrace:
        tail.quantity = layer.parameter
    elif tail_type is H7025DiyBody.Spray:
        tail.variant = layer.parameter
        tail.injections, tail.interval = layer.points
    elif tail_type in (H7025DiyBody.Streamer, H7025DiyBody.PileUp):
        tail.direction, tail.reverse = layer.parameter, layer.flag
    elif tail_type is H7025DiyBody.Glimmer:
        tail.density = layer.parameter
    else:
        tail.density = layer.parameter
        tail.background = new_rgb(tail, layer.secondary_palette[0])
    body.tail = tail
    return serialize_native_body(body)


def decode_h7025_diy(payload: bytes) -> NativeEffect:
    try:
        body = H7025DiyBody.Body.from_bytes(payload)
        body._read()
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError("invalid H7025 native DIY body") from error
    tail = body.tail
    kind = int(body.sub_effect)
    preset: int
    parameter: int
    flag: int
    points: tuple[int, ...]
    background: tuple[tuple[int, int, int], ...]
    if kind == H7025DiyBody.SubEffect.retrace:
        preset, parameter, flag, points, background = 16, int(tail.quantity), 0, (), ()
    elif kind == H7025DiyBody.SubEffect.spray:
        preset = 16 + int(tail.variant)
        parameter, flag, points, background = int(tail.variant), 0, (int(tail.injections), int(tail.interval)), ()
    elif kind == H7025DiyBody.SubEffect.glimmer:
        preset, parameter, flag, points, background = 21, int(tail.density), 0, (), ()
    elif kind == H7025DiyBody.SubEffect.star_flash:
        preset = 22
        parameter, flag, points, background = int(tail.density), 0, (), (_rgb(tail.background),)
    else:
        flag = int(tail.reverse)
        preset = (19 if kind == H7025DiyBody.SubEffect.streamer else 23) + flag
        parameter, points, background = int(tail.direction), (), ()
    layer = NativeDiyLayer(
        kind=kind,
        speed=int(tail.speed),
        palette=tuple(_rgb(colour) for colour in tail.palette.colours),
        parameter=parameter,
        flag=flag,
        points=points,
        secondary_palette=background,
    )
    result = NativeEffect(
        family=H7025_NATIVE_DIY_FAMILY,
        layers=(layer,),
        preset_id=preset,
        model="H7025",
    )
    validate_h7025_diy(result)
    return result
