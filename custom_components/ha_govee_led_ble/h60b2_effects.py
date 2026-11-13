"""Semantic adapter for length-delimited native palette effects."""

import io

from kaitaistruct import KaitaiStream

from .native_effect import NativeDiyLayer, NativeEffect
from .protocol_core import H60b2DiyBody, new_child, new_rgb, serialize_native_body


def encode_h60b2_diy(content: NativeEffect) -> bytes:
    content.__post_init__()
    layer = content.layers[0]
    if content.model != "H60B2" or not isinstance(layer, NativeDiyLayer):
        raise ValueError("native palette content does not match the codec")
    if (
        not layer.enabled
        or layer.parameters
        or layer.flag
        or layer.points
        or layer.direction
        or layer.angle
        or layer.opaque
        or layer.secondary_palette
        or layer.temperatures
    ):
        raise ValueError("native palette contains unrepresented parameters")
    root = H60b2DiyBody()
    root.body = new_child(H60b2DiyBody.Body, root)
    body = root.body
    body.variant = H60b2DiyBody.Variant(layer.kind)
    body.direction = (
        H60b2DiyBody.Direction(layer.parameter)
        if body.variant
        in {
            H60b2DiyBody.Variant.chase,
            H60b2DiyBody.Variant.bloom,
            H60b2DiyBody.Variant.stream,
        }
        else None
    )
    if body.direction is None and layer.parameter:
        raise ValueError("native variant has no direction")
    body.speed = layer.speed
    body.num_palette = len(layer.palette)
    body.palette = [new_rgb(body, colour) for colour in layer.palette]
    body.unknown_tail = b""
    root.len_body = len(serialize_native_body(body))
    body._io = KaitaiStream(io.BytesIO(bytes(root.len_body)))
    root.unknown_tail = b""
    return serialize_native_body(root)
