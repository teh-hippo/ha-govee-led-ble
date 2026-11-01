"""Semantic transforms for independently bounded native DIY zones."""

import io
from math import ceil
from typing import Any

from kaitaistruct import KaitaiStream

from .native_effect import NativeDiyLayer, NativeEffect, NativeLayer, NativeOpaqueLayer
from .protocol_core import (
    H607cDiyBody,
    H607cMusicBody,
    H607cMusicWrite,
    _serialize_a3_scene_param,
    new_child,
    new_rgb,
    serialize_native_body,
)


def _palette(parent: Any, colours: tuple[tuple[int, int, int], ...]) -> Any:
    value = new_child(H607cDiyBody.Palette, parent)
    value.num_colours = len(colours)
    value.colours = [new_rgb(value, colour) for colour in colours]
    return value


def _parameters(layer: NativeDiyLayer | NativeOpaqueLayer, parent: Any) -> Any:
    if isinstance(layer, NativeOpaqueLayer):
        value = H607cDiyBody.Parameters(
            layer.kind, KaitaiStream(io.BytesIO(layer.data)), _parent=parent, _root=parent._root
        )
        value._read()
        return value
    if layer.parameters or layer.flag or layer.points or layer.direction or layer.angle:
        raise ValueError("unrepresented native DIY parameters")
    if layer.kind not in H607cDiyBody.Family or layer.kind == H607cDiyBody.Family.paired:
        raise ValueError("unsupported independent native DIY family")
    value = H607cDiyBody.Parameters(layer.kind, _parent=parent, _root=parent._root)
    value.variant, value.speed = layer.parameter, layer.speed
    value.unknown_tail = layer.opaque
    value.first_palette = _palette(value, layer.palette)
    if layer.kind in (H607cDiyBody.Family.shimmer, H607cDiyBody.Family.drip):
        value.second_palette = _palette(value, layer.secondary_palette)
    return value


def _decode_parameters(kind: int, value: Any) -> NativeDiyLayer | NativeOpaqueLayer:
    if value.speed > 100:
        return NativeOpaqueLayer(kind, serialize_native_body(value))
    secondary = getattr(value, "second_palette", None)
    return NativeDiyLayer(
        kind=kind,
        speed=int(value.speed),
        parameter=int(value.variant),
        palette=tuple((int(colour.red), int(colour.green), int(colour.blue)) for colour in value.first_palette.colours),
        secondary_palette=tuple((int(colour.red), int(colour.green), int(colour.blue)) for colour in secondary.colours)
        if secondary is not None
        else (),
        opaque=value.unknown_tail,
    )


def decode_zoned_diy(payload: bytes) -> NativeEffect:
    root = H607cDiyBody.from_bytes(payload)
    root._read()
    if root.family not in H607cDiyBody.Family:
        raise ValueError("unknown native DIY family")
    layers: list[NativeLayer] = []
    if root.family == H607cDiyBody.Family.paired:
        for zone in (root.body.pole, root.body.base):
            if zone.len_body == 0:
                layers.append(NativeDiyLayer(int(zone.family), 0, (), enabled=False))
            elif isinstance(zone.body, bytes):
                layers.append(NativeOpaqueLayer(int(zone.family), zone.body))
            else:
                layers.append(_decode_parameters(int(zone.family), zone.body))
    else:
        layers.append(_decode_parameters(int(root.family), root.body))
    return NativeEffect(
        model="H607C",
        family=int(root.family),
        layers=tuple(layers),
        opaque=root.body.unknown_tail if root.family == H607cDiyBody.Family.paired else root.unknown_tail,
    )


def encode_zoned_diy(content: NativeEffect) -> bytes:
    content.__post_init__()
    root = H607cDiyBody()
    root.marker = b"\x0b"
    root.family = H607cDiyBody.Family(content.family)
    root.unknown_tail = b""
    if root.family == H607cDiyBody.Family.paired:
        root.body = new_child(H607cDiyBody.PairedParameters, root)
        root.body.unknown_tail = content.opaque
        for name, layer in zip(("pole", "base"), content.layers, strict=True):
            if not isinstance(layer, NativeDiyLayer | NativeOpaqueLayer):
                raise ValueError("native DIY requires independently bounded zone parameters")
            zone = new_child(H607cDiyBody.Zone, root.body)
            if isinstance(layer, NativeDiyLayer) and not layer.enabled:
                zone.family, zone.len_body, zone.body = 0, 0, None
            else:
                zone.family = layer.kind
                if (layer.kind not in H607cDiyBody.Family or layer.kind == H607cDiyBody.Family.paired) and isinstance(
                    layer, NativeOpaqueLayer
                ):
                    zone.body, zone.len_body = layer.data, len(layer.data)
                else:
                    zone.body = _parameters(layer, zone)
                    zone.len_body = len(serialize_native_body(zone.body))
            setattr(root.body, name, zone)
    else:
        layer = content.layers[0]
        if not isinstance(layer, NativeDiyLayer | NativeOpaqueLayer):
            raise ValueError("native DIY requires its parameter body")
        if layer.kind != root.family or isinstance(layer, NativeDiyLayer) and not layer.enabled:
            raise ValueError("single native DIY must retain its enabled family")
        if content.opaque:
            raise ValueError("single native DIY extensions belong to its parameter body")
        root.body = _parameters(layer, root)
    return serialize_native_body(root)


def _music_parameters(
    parent: Any,
    mode: int,
    palette: tuple[tuple[int, int, int], ...],
    unknown: bytes,
    ic_count: int | None,
) -> Any:
    if mode == H607cMusicWrite.MusicMode.paired:
        raise ValueError("paired music zones cannot contain another paired mode")
    value = H607cMusicBody.Parameters(mode, _parent=parent, _root=parent._root)
    value.num_palette = len(palette)
    value.palette = [new_rgb(value, colour) for colour in palette]
    if mode == H607cMusicWrite.MusicMode.hopping:
        if ic_count is None or ic_count < 1:
            raise ValueError("Hopping parameters require a physical zone budget")
        tail = new_child(H607cMusicBody.HoppingParameters, value)
        tail.background = new_rgb(tail, (0, 0, 0))
        tail.background_brightness, tail.speed = 25, 98
        tail.piece_length_min, tail.piece_length_max = 1, 3
        tail.piece_count_min, tail.piece_count_max = max(1, ceil(ic_count * 3 / 25)), max(1, ceil(ic_count * 2 / 5))
        tail.unknown_tail = unknown
    else:
        tail = new_child(H607cMusicBody.OpaqueParameters, value)
        tail.unknown = unknown
    value.tail = tail
    return value


def music_template(
    mode: int,
    palette: tuple[tuple[int, int, int], ...] = (),
    unknown: bytes = b"",
    *,
    ic_count: int | None = None,
    zones: tuple[tuple[int, tuple[tuple[int, int, int], ...], bytes, int | None], ...] = (),
) -> bytes:
    """Build variant seeds through generated fields, including each zone's length."""
    root = H607cMusicBody()
    root.command = b"\x41"
    root.mode = H607cMusicWrite.MusicMode(mode)
    root.padding = []
    if root.mode == H607cMusicWrite.MusicMode.paired:
        if len(zones) != 2 or palette or unknown:
            raise ValueError("paired music requires exactly two independent zones")
        root.body = new_child(H607cMusicBody.PairedParameters, root)
        for name, (zone_mode, colours, opaque, physical_count) in zip(("pole", "base"), zones, strict=True):
            zone = new_child(H607cMusicBody.Zone, root.body)
            zone.mode = H607cMusicWrite.MusicMode(zone_mode)
            zone.body = _music_parameters(zone, zone_mode, colours, opaque, physical_count)
            zone.len_parameters = len(serialize_native_body(zone.body))
            setattr(root.body, name, zone)
    else:
        if zones:
            raise ValueError("ordinary music does not have paired zones")
        root.body = _music_parameters(root, mode, palette, unknown, ic_count)
    return _serialize_a3_scene_param(root)
