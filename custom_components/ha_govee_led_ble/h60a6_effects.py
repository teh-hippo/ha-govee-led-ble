"""Semantic transforms for the native H60A6 effect grammars."""

from __future__ import annotations

import io
from dataclasses import replace
from typing import Any

from kaitaistruct import KaitaiStream, KaitaiStructError

from .layered_scene import CatalogueRef
from .native_effect import (
    NativeDiyLayer,
    NativeEffect,
    NativeLayer,
    NativeOpaqueLayer,
    NativePaintGroup,
    NativePaintLayer,
)
from .protocol_core import GoveeShared, H60a6DiyBody, H60a6PaintBody


def _rgb(value: Any) -> tuple[int, int, int]:
    return int(value.red), int(value.green), int(value.blue)


def decode_native_scene(scene_ref: CatalogueRef, payload: bytes, *, family: int) -> NativeEffect:
    """Decode catalogue bytes without discarding their scene activation identity."""
    return replace(decode_native_body(payload, family=family), template=scene_ref)


def decode_native_body(payload: bytes, *, family: int) -> NativeEffect:
    if family not in (797, 798):
        raise ValueError("unknown native effect family")
    root_type = H60a6DiyBody if family == 797 else H60a6PaintBody
    stream = KaitaiStream(io.BytesIO(payload))
    root = root_type(stream)
    try:
        root._read()
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError(f"invalid native effect body: {error}") from error
    if stream.pos() != len(payload):
        raise ValueError("native body length does not match its envelope")
    if family == 797:
        data = root.payload
        layers: list[NativeLayer] = []
        for layer in data.layers:
            body = layer.body
            if isinstance(body, H60a6DiyBody.OpaqueBody):
                layers.append(NativeOpaqueLayer(int(layer.kind), bytes(body.data)))
                continue
            layers.append(
                NativeDiyLayer(
                    kind=int(layer.kind),
                    speed=int(body.speed),
                    palette=tuple(_rgb(colour) for colour in body.palette.colours),
                    parameters=bytes(getattr(body, "unknown_parameters", b"")),
                    parameter=int(getattr(body, "unknown_parameter", 0)),
                    flag=int(getattr(body, "unknown_flag", 0)),
                    points=tuple(getattr(body, "points", ())),
                    direction=int(getattr(body, "direction", 0)),
                    angle=int(getattr(body, "angle", 0)),
                    opaque=bytes(body.opaque),
                )
            )
        return NativeEffect(
            family=family,
            layers=tuple(layers),
            backgrounds=tuple(_rgb(colour) for colour in data.backgrounds),
            background_flag=int(data.background_flag),
            opaque=bytes(data.opaque),
        )
    paint_layers: list[NativeLayer] = []
    for layer in root.layers:
        body = layer.body
        if isinstance(body, H60a6PaintBody.OpaqueBody):
            paint_layers.append(NativeOpaqueLayer(int(layer.kind), bytes(body.data)))
            continue
        paint_layers.append(
            NativePaintLayer(
                groups=tuple(NativePaintGroup(_rgb(group.colour), tuple(group.indices)) for group in body.data.groups),
                action=int(body.action),
                speed=int(body.speed),
                brightness=int(body.brightness),
                priority=int(body.priority),
                duration=int(body.duration),
                opaque=bytes(body.opaque),
                data_opaque=bytes(body.data.opaque),
                trailing=bytes(body.trailing),
            )
        )
    return NativeEffect(
        family=family,
        layers=tuple(paint_layers),
        background=_rgb(root.background),
        background_brightness=int(root.background_brightness),
        show_type=int(root.show_type),
        opaque=bytes(root.opaque),
    )


def _new(cls: Any, parent: Any, root: Any, **fields: Any) -> Any:
    value = cls(_parent=parent, _root=root)
    for name, field in fields.items():
        setattr(value, name, field)
    return value


def _colour(colour: tuple[int, int, int]) -> Any:
    value = GoveeShared.Rgb()
    value.red, value.green, value.blue = colour
    return value


def _serialise(value: Any) -> bytes:
    from .protocol_core import serialize_native_body

    try:
        return serialize_native_body(value)
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError(f"invalid native effect structure: {error}") from error


def encode_native_body(content: NativeEffect) -> bytes:
    """Build all lengths and byte order through generated native structures."""
    content.__post_init__()
    if content.family == 797:
        root = H60a6DiyBody()
        root.marker = b"\x50"
        data = _new(
            H60a6DiyBody.Payload,
            root,
            root,
            layer_count=len(content.layers),
            background_count=len(content.backgrounds),
            backgrounds=[_colour(colour) for colour in content.backgrounds],
            background_flag=content.background_flag,
            opaque=content.opaque,
        )
        data.layers = [_diy_layer(layer, data, root) for layer in content.layers]
        root.payload = data
        root.payload_length = len(_serialise(data))
    else:
        root = H60a6PaintBody()
        root.marker = b"\x50\x20"
        root.background = _colour(content.background)
        root.background_brightness = content.background_brightness
        root.show_type = content.show_type
        root.layer_count = len(content.layers)
        root.layers = [_paint_layer(layer, root) for layer in content.layers]
        root.opaque = content.opaque
    return _serialise(root)


def _diy_layer(content: Any, parent: Any, root: Any) -> Any:
    layer = _new(H60a6DiyBody.Layer, parent, root, kind=content.kind)
    if isinstance(content, NativeOpaqueLayer):
        layer.body = _new(H60a6DiyBody.OpaqueBody, layer, root, data=content.data)
    else:
        kind = H60a6DiyBody.LayerKind(content.kind)
        body_type = (
            H60a6DiyBody.SingleParameter
            if kind in (H60a6DiyBody.LayerKind.fade, H60a6DiyBody.LayerKind.breathing, H60a6DiyBody.LayerKind.flashing)
            else getattr(H60a6DiyBody, "".join(part.title() for part in kind.name.split("_")))
        )
        body = _new(body_type, layer, root, speed=content.speed, opaque=content.opaque)
        if kind == H60a6DiyBody.LayerKind.rotation:
            body.direction, body.angle, body.unknown_flag = content.direction, content.angle, content.flag
        elif kind in (H60a6DiyBody.LayerKind.fade, H60a6DiyBody.LayerKind.breathing, H60a6DiyBody.LayerKind.flashing):
            body.unknown_parameter = content.parameter
        else:
            body.unknown_parameters = content.parameters
            if kind == H60a6DiyBody.LayerKind.line_flow:
                body.unknown_parameter, body.unknown_flag = content.parameter, content.flag
                body.point_count, body.points = len(content.points), list(content.points)
        body.palette = _new(
            H60a6DiyBody.Palette,
            body,
            root,
            colour_count=len(content.palette),
            colours=[_colour(colour) for colour in content.palette],
        )
        layer.body = body
    layer.length = len(_serialise(layer.body)) + 1
    return layer


def _paint_layer(content: Any, root: Any) -> Any:
    layer = _new(
        H60a6PaintBody.Layer,
        root,
        root,
        kind=content.kind if isinstance(content, NativeOpaqueLayer) else H60a6PaintBody.LayerKind.point_groups,
    )
    if isinstance(content, NativeOpaqueLayer):
        layer.body = _new(H60a6PaintBody.OpaqueBody, layer, root, data=content.data)
    else:
        body = _new(
            H60a6PaintBody.PointGroups,
            layer,
            root,
            action=content.action,
            speed=content.speed,
            brightness=content.brightness,
            priority=content.priority,
            duration=content.duration,
            opaque=content.opaque,
            trailing=content.trailing,
        )
        data = _new(
            H60a6PaintBody.ColourGroups, body, root, group_count=len(content.groups), opaque=content.data_opaque
        )
        data.groups = [
            _new(
                H60a6PaintBody.ColourGroup,
                data,
                root,
                point_count=len(group.indices),
                colour=_colour(group.colour),
                indices=list(group.indices),
            )
            for group in content.groups
        ]
        body.data = data
        body.data_length = len(_serialise(data))
        layer.body = body
    layer.length = len(_serialise(layer.body)) + 1
    return layer


def native_diy_preset(preset_id: int, palette: tuple[tuple[int, int, int], ...]) -> NativeEffect:
    """Create exact native preset structures without reinterpreting unknown parameters."""
    kind = H60a6DiyBody.LayerKind
    layers: tuple[NativeDiyLayer, ...]
    if preset_id == 1:
        layers = tuple(
            NativeDiyLayer(kind.area_flow, 50, palette, parameters=bytes.fromhex(parameters))
            for parameters in ("ce003232040000000064640101", "9c003232040000000064640101")
        )
    elif preset_id in (2, 3, 4):
        layers = (
            NativeDiyLayer(
                kind.line_flow,
                50,
                palette,
                parameters=bytes.fromhex("6464010100"),
                parameter={2: 8, 3: 9, 4: 10}[preset_id],
                flag=1,
                points=(1, 61),
            ),
        )
    elif preset_id in (5, 6):
        layers = (
            NativeDiyLayer(
                kind.spread_gather,
                50,
                palette,
                parameters=bytes.fromhex("01050664640101" if preset_id == 5 else "01050564640101"),
            ),
        )
    elif preset_id in (7, 8):
        layers = (NativeDiyLayer(kind.rotation, 50, palette, direction=8, angle=90, flag=int(preset_id == 8)),)
    elif preset_id in (9, 10):
        layers = (
            NativeDiyLayer(
                kind.random_breathing,
                100 if preset_id == 9 else 50,
                palette,
                parameters=bytes((10, int(preset_id == 9))),
            ),
        )
    elif preset_id in (11, 12):
        layers = (
            NativeDiyLayer(
                kind.meteor,
                100,
                palette,
                parameters=bytes((8, 5, 3, 5, int(preset_id == 11))),
            ),
        )
    elif preset_id == 13:
        layers = (NativeDiyLayer(kind.random_gradient, 50, palette, parameters=bytes((1, 12))),)
    elif preset_id == 14:
        layers = (NativeDiyLayer(kind.fade, 50, palette, parameter=1),)
    elif preset_id == 15:
        return NativeEffect(family=798, layers=(NativePaintLayer(groups=()),), preset_id=preset_id)
    else:
        raise ValueError("unknown native DIY preset")
    return NativeEffect(
        family=797,
        layers=layers,
        backgrounds=((0, 0, 255),),
        background_flag=5 if preset_id in (9, 11, 12) else 15,
        preset_id=preset_id,
    )
