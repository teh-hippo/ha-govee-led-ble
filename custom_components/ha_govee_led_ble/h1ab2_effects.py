"""Semantic codec for the native Accumulation wire format."""

from .native_effect import NativeDiyLayer, NativeEffect
from .protocol_core import H1ab2DiyBody, new_rgb, serialize_native_body


def encode_accumulation(content: NativeEffect) -> bytes:
    content.__post_init__()
    layer = content.layers[0]
    assert isinstance(layer, NativeDiyLayer)
    variation = H1ab2DiyBody.Variation(layer.parameter)
    root = H1ab2DiyBody()
    root.effect = H1ab2DiyBody.Effect.accumulation
    root.speed = layer.speed
    root.direction = (
        H1ab2DiyBody.Direction.counter_clockwise
        if variation in (H1ab2DiyBody.Variation.counter_clockwise, H1ab2DiyBody.Variation.counter_clockwise_return)
        else H1ab2DiyBody.Direction.clockwise
    )
    root.return_enabled = int(
        variation in (H1ab2DiyBody.Variation.clockwise_return, H1ab2DiyBody.Variation.counter_clockwise_return)
    )
    root.num_palette = len(layer.palette)
    root.palette = [new_rgb(root, rgb) for rgb in layer.palette]
    return serialize_native_body(root)


def decode_accumulation(payload: bytes) -> NativeEffect:
    root = H1ab2DiyBody.from_bytes(payload)
    root._read()
    if (
        not root._io.is_eof()
        or root.effect != H1ab2DiyBody.Effect.accumulation
        or root.direction not in H1ab2DiyBody.Direction
        or root.return_enabled not in (0, 1)
    ):
        raise ValueError("unqualified native Accumulation parameters")
    variation = (
        H1ab2DiyBody.Variation.counter_clockwise_return
        if root.return_enabled and root.direction == H1ab2DiyBody.Direction.counter_clockwise
        else H1ab2DiyBody.Variation.clockwise_return
        if root.return_enabled
        else H1ab2DiyBody.Variation.counter_clockwise
        if root.direction == H1ab2DiyBody.Direction.counter_clockwise
        else H1ab2DiyBody.Variation.clockwise
    )
    return NativeEffect(
        model="H1AB2",
        family=int(H1ab2DiyBody.CatalogueFamily.accumulation),
        layers=(
            NativeDiyLayer(
                kind=int(root.effect),
                speed=int(root.speed),
                parameter=int(variation),
                palette=tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in root.palette),
            ),
        ),
    )
