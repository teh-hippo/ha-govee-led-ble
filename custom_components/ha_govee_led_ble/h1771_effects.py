"""Semantic transforms for H1771's independently bounded DIY sections."""

import io
from typing import Any

from kaitaistruct import KaitaiStream, KaitaiStructError

from .native_effect import NativeDiyLayer, NativeEffect, NativeLayer, NativeOpaqueLayer
from .protocol_core import H1771DiyBody, new_child, new_rgb, serialize_native_body

_FIRST = H1771DiyBody.FirstEffect
_SECOND = H1771DiyBody.SecondEffect
_FIRST_TYPES = {
    _FIRST.temperature: H1771DiyBody.Temperature,
    _FIRST.palette_2: H1771DiyBody.SpeedPalette,
    _FIRST.palette_3: H1771DiyBody.SpeedPalette,
    _FIRST.palette_4: H1771DiyBody.SpeedPalette,
}
_SECOND_TYPES = {
    **{
        effect: H1771DiyBody.CommonPalette
        for effect in (_SECOND.common_1, _SECOND.common_2, _SECOND.common_3, _SECOND.common_4, _SECOND.common_5)
    },
    **{effect: H1771DiyBody.SpeedPalette for effect in (_SECOND.palette_6, _SECOND.palette_13, _SECOND.palette_14)},
    **{effect: H1771DiyBody.TwoParameterPalette for effect in (_SECOND.streamer, _SECOND.stack, _SECOND.breathe)},
    _SECOND.background: H1771DiyBody.BackgroundPalette,
    _SECOND.temperature: H1771DiyBody.Temperature,
}


def _rgb(value: Any) -> tuple[int, int, int]:
    return int(value.red), int(value.green), int(value.blue)


def _decode_section(section: Any, raw: bytes) -> NativeLayer:
    enabled = getattr(section, "enabled", None)
    if enabled is None or enabled == 0:
        return NativeDiyLayer(0, 0, (), enabled=False, opaque=raw)
    kind = int(getattr(section, "effect", 0))
    body = getattr(section, "body", None)
    if enabled != 1 or body is None or isinstance(body, bytes) or int(body.speed) > 100:
        return NativeOpaqueLayer(kind, raw)
    palette = getattr(body, "palette", None)
    background = getattr(body, "background", None)
    return NativeDiyLayer(
        kind=kind,
        speed=int(body.speed),
        palette=tuple(_rgb(colour) for colour in palette.colours) if palette is not None else (),
        parameter=int(getattr(body, "brightness", getattr(body, "variant", getattr(body, "parameter_1", 0)))),
        flag=int(getattr(body, "parameter_2", 0)),
        angle=int(getattr(body, "kelvin", 0)),
        secondary_palette=(_rgb(background),) if background is not None else (),
        opaque=bytes(body.unknown_tail),
    )


def decode_h1771_diy(payload: bytes) -> NativeEffect:
    try:
        root = H1771DiyBody.from_bytes(payload)
        root._read()
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError("invalid native dual-source DIY body") from error
    sections = root.body
    return NativeEffect(
        model="H1771",
        family=int(H1771DiyBody.CatalogueFamily.native_scene),
        layers=(
            _decode_section(sections.first, sections._raw_first),
            _decode_section(sections.second, sections._raw_second),
        ),
        section_tail=bytes(sections.unknown_tail),
        opaque=bytes(root.unknown_tail),
    )


def decode_h1771_scene(payload: bytes) -> NativeEffect:
    try:
        scene = H1771DiyBody.Scene(KaitaiStream(io.BytesIO(payload)), _root=H1771DiyBody())
        scene._read()
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError("invalid native dual-source scene") from error
    return decode_h1771_diy(serialize_native_body(scene.body))


def _body(layer: NativeDiyLayer, section: Any, body_type: Any) -> Any:
    if layer.parameters or layer.points or layer.direction:
        raise ValueError("unrepresented native DIY parameters")
    body = new_child(body_type, section)
    body.speed = layer.speed
    body.unknown_tail = layer.opaque
    if body_type is H1771DiyBody.Temperature:
        if layer.palette or layer.secondary_palette or layer.flag:
            raise ValueError("temperature section contains incompatible parameters")
        body.brightness, body.kelvin = layer.parameter, layer.angle
    else:
        if layer.angle:
            raise ValueError("palette section cannot contain a colour temperature")
        body.palette = new_child(H1771DiyBody.Palette, body)
        body.palette.num_colours = len(layer.palette)
        body.palette.colours = [new_rgb(body.palette, colour) for colour in layer.palette]
        if body_type is H1771DiyBody.CommonPalette:
            body.variant = layer.parameter
        elif body_type is H1771DiyBody.TwoParameterPalette:
            body.parameter_1, body.parameter_2 = layer.parameter, layer.flag
        elif layer.parameter or layer.flag:
            raise ValueError("palette section contains unsupported parameters")
        if body_type is H1771DiyBody.BackgroundPalette:
            if len(layer.secondary_palette) != 1:
                raise ValueError("background effect requires exactly one background colour")
            body.background = new_rgb(body, layer.secondary_palette[0])
        elif layer.secondary_palette:
            raise ValueError("this effect does not have a background colour")
    return body


def _section(layer: NativeLayer, parent: Any, *, first: bool) -> tuple[Any, int]:
    section_type = H1771DiyBody.FirstSection if first else H1771DiyBody.SecondSection
    types = _FIRST_TYPES if first else _SECOND_TYPES
    if isinstance(layer, NativeOpaqueLayer) or isinstance(layer, NativeDiyLayer) and not layer.enabled:
        raw = layer.data if isinstance(layer, NativeOpaqueLayer) else layer.opaque
        section = section_type(KaitaiStream(io.BytesIO(raw)), parent, parent._root)
        section._read()
        if isinstance(layer, NativeDiyLayer) and getattr(section, "enabled", 0) != 0:
            raise ValueError("disabled section retains an enabled body")
        return section, len(raw)
    if not isinstance(layer, NativeDiyLayer) or layer.kind not in types:
        raise ValueError("unsupported native DIY section effect")
    section = new_child(section_type, parent)
    section.enabled = 1
    section.effect = layer.kind
    section.body = _body(layer, section, types[layer.kind])
    section.unknown_tail = b""
    length = 2 + len(serialize_native_body(section.body))
    section._io = KaitaiStream(io.BytesIO(bytes(length)))
    return section, length


def encode_h1771_diy(content: NativeEffect) -> bytes:
    content.__post_init__()
    if content.model != "H1771":
        raise ValueError("native dual-source DIY does not match the model")
    root = H1771DiyBody()
    root.body = new_child(H1771DiyBody.Sections, root)
    root.body.first, root.body.len_first = _section(content.layers[0], root.body, first=True)
    root.body.second, root.body.len_second = _section(content.layers[1], root.body, first=False)
    root.body.unknown_tail = content.section_tail
    root.len_body = 4 + root.body.len_first + root.body.len_second + len(content.section_tail)
    root.unknown_tail = content.opaque
    return serialize_native_body(root)


def encode_h1771_scene(content: NativeEffect) -> bytes:
    body = encode_h1771_diy(content)
    root = H1771DiyBody()
    scene = H1771DiyBody.Scene(_root=root)
    scene.marker = b"\x50"
    scene.body = H1771DiyBody(KaitaiStream(io.BytesIO(body)), scene, root)
    scene.body._read()
    return serialize_native_body(scene)
