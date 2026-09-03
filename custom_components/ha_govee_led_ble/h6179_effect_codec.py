"""H6179 DIY effect encoding and decoding through the generated Kaitai tree."""

from __future__ import annotations

import io
from typing import Any, cast

from kaitaistruct import KaitaiStream, KaitaiStructError

from .effect_domain import EffectContent, EffectPair, H6179MixedDiyEffect, H6179SingleDiyEffect
from .generated_protocol_adapter import GoveeShared, H6179DiyBody, check_generated_tree, new_child


class H6179EffectCodecError(ValueError):
    """An H6179 DIY body cannot be encoded or represented canonically."""


def encode_h6179_effect(content: H6179SingleDiyEffect | H6179MixedDiyEffect) -> bytes:
    root = H6179DiyBody()
    root.marker = b"\xfe"
    root.opaque = b""

    if isinstance(content, H6179SingleDiyEffect):
        root.family = content.family
        body = new_child(H6179DiyBody.SingleBody, root)
    else:
        root.family = 0xFF
        body = new_child(H6179DiyBody.MixedBody, root)

    body.variant = 0 if isinstance(content, H6179MixedDiyEffect) else content.variant
    body.speed = content.speed
    body.len_palette = len(content.palette) * 3
    body.palette = _palette(body, content.palette)
    if isinstance(content, H6179MixedDiyEffect):
        body.mix_bytes = len(content.components) * 2
        body.pairs = [_effect_pair(body, component) for component in content.components]
    root.body = body

    check_generated_tree(root)
    length = 5 + body.len_palette
    if isinstance(content, H6179MixedDiyEffect):
        length += 1 + body.mix_bytes
    stream = KaitaiStream(io.BytesIO(bytes(length)))
    root._write(stream)
    return cast(bytes, stream.to_byte_array())


def decode_h6179_effect(body: bytes) -> EffectContent:
    try:
        stream = KaitaiStream(io.BytesIO(body))
        root = H6179DiyBody(stream)
        root._read()
    except KaitaiStructError as error:
        raise H6179EffectCodecError("invalid H6179 DIY body") from error
    if not stream.is_eof():
        raise H6179EffectCodecError("H6179 DIY grammar did not consume the body")

    try:
        if any(root.opaque):
            raise ValueError("H6179 DIY body contains non-zero opaque trailing bytes")
        if root.family == 0xFF:
            if root.body.variant != 0 or root.body.mix_bytes != len(root.body.pairs) * 2:
                raise ValueError("H6179 mixed DIY lengths are not canonical")
            return H6179MixedDiyEffect(
                model="H6179",
                components=tuple(EffectPair(int(pair.family), pair.variant) for pair in root.body.pairs),
                speed=root.body.speed,
                palette=_decoded_palette(root.body),
            )
        if root.family not in {0, 1, 2}:
            raise ValueError(f"unsupported H6179 DIY family {root.family}")
        return H6179SingleDiyEffect(
            model="H6179",
            family=int(root.family),
            variant=root.body.variant,
            speed=root.body.speed,
            palette=_decoded_palette(root.body),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise H6179EffectCodecError("H6179 DIY body has unsupported semantics") from error


def _palette(parent: Any, colours: tuple[tuple[int, int, int], ...]) -> Any:
    palette = new_child(H6179DiyBody.Palette, parent)
    palette.colours = []
    for red, green, blue in colours:
        colour = new_child(GoveeShared.Rgb, palette)
        colour.red, colour.green, colour.blue = red, green, blue
        palette.colours.append(colour)
    return palette


def _effect_pair(parent: Any, component: EffectPair) -> Any:
    pair = new_child(H6179DiyBody.EffectPair, parent)
    pair.family = component.family
    pair.variant = component.variant
    return pair


def _rgb(colour: Any) -> tuple[int, int, int]:
    return int(colour.red), int(colour.green), int(colour.blue)


def _decoded_palette(body: Any) -> tuple[tuple[int, int, int], ...]:
    palette = tuple(_rgb(colour) for colour in body.palette.colours)
    if body.len_palette != len(palette) * 3:
        raise ValueError("H6179 DIY palette length is not canonical")
    return palette
