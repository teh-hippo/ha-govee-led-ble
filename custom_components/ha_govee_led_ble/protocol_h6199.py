"""H6199 control, palette DIY and scene adapters."""

from __future__ import annotations

import io
from typing import Any

from kaitaistruct import KaitaiStream

from .protocol_core import (
    _A3_MAX_CONTENT,
    H6199CommandWrite,
    H6199ControlPayload,
    H6199EffectUpload,
    SceneParameterTooLargeError,
    _child,
    _serialize_xor,
    _serialized_length,
    _set_effect_layer_lengths,
    _write,
    check_generated_tree,
    new_rgb,
)
from .transport import (
    A3_CHUNK_SIZE,
)

INSTALLATION_DIRECTIONS = (2, 3, 4, 5)


H6199_NATIVE_CONTROLS = ("strip_direction", "camera_position", "gradient", "camera_status")


def build_h6199_control_query(control: str) -> bytes:
    """Encode a named register query; callers must check runtime applicability."""

    from .generated_protocol_adapter import _build_status_query

    if control not in H6199_NATIVE_CONTROLS:
        raise ValueError("Unknown H6199 control")
    return _build_status_query(control, "H6199")


def build_h6199_control(control: str, value: int) -> bytes:
    """Encode an independently writable register, without changing the active mode."""
    if control not in H6199_NATIVE_CONTROLS[:-1] or type(value) is not int or value not in (0, 1):
        raise ValueError("H6199 control requires a writable setting and integer 0 or 1")
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = getattr(H6199CommandWrite.CommandOp, control)
    root.body = _child(H6199ControlPayload.WriteValue, root)
    root.body.value = value
    root.body.unknown_tail = bytes(16)
    return _serialize_xor(root)


def parse_h6199_control(generated: Any) -> dict[str, int | str | None]:
    """Read named generated fields, retaining unknown state rather than coercing it."""
    control = getattr(generated.domain, "name", None)
    if control in H6199_NATIVE_CONTROLS:
        value = generated.body.value
        if control == "camera_status":
            return {control: getattr(value, "name", "unknown")}
        return {control: int(value) if value in (0, 1) else None}
    if control == "colour_mode" and getattr(generated.body.mode, "name", None) == "static_colour":
        value = generated.body.detail.gradient
        return {"gradient": int(value) if value in (0, 1) else None}
    return {}


def h6199_diy_padding_len(palette_size: int) -> int:
    """Return the zero padding required by the captured two-chunk DIY envelope."""
    if not isinstance(palette_size, int) or isinstance(palette_size, bool) or palette_size < 0:
        raise ValueError("H6199 DIY palette size must be a non-negative integer")
    root = H6199EffectUpload()
    content = _child(H6199EffectUpload.DiyContent, root)
    content.palette_len = palette_size * 3
    padding_len = int(content.padding_len)
    if padding_len < 0:
        raise ValueError("H6199 DIY palette does not fit the fixed two-chunk envelope")
    return padding_len


def build_h6199_palette_diy_envelope(
    family: int,
    variant: int,
    speed: int,
    palette: tuple[tuple[int, int, int], ...],
) -> bytes:
    root = H6199EffectUpload()
    root.header = b"\x01"
    root.chunk_count = root.diy_chunk_count
    root.kind = H6199EffectUpload.BodyKind.diy
    content = _child(H6199EffectUpload.DiyContent, root)
    content.family = KaitaiStream.resolve_enum(H6199EffectUpload.EffectFamily, family)
    content.variant = variant
    content.speed = speed
    content.palette_len = len(palette) * 3
    content.palette = [new_rgb(content, colour) for colour in palette]
    root.content = content
    content.padding = [0] * h6199_diy_padding_len(len(palette))
    check_generated_tree(root)
    return _write(root, root.diy_chunk_count * A3_CHUNK_SIZE)


def parse_h6199_workshop_content(raw_param: bytes) -> tuple[Any, int]:
    """Parse an H6199 Workshop parameter through the generated effect-upload content."""
    if not isinstance(raw_param, bytes):
        raise TypeError("Workshop parameter must be bytes")
    root = H6199EffectUpload()
    parsed = H6199EffectUpload.SceneContent(KaitaiStream(io.BytesIO(raw_param)), root, root)
    parsed._read()
    return parsed, len(parsed.padding)


def serialize_h6199_workshop_content(content: Any) -> bytes:
    """Serialize built H6199 Workshop content without its A3 envelope."""
    _set_effect_layer_lengths(content.blocks)
    check_generated_tree(content)
    content_size = _serialized_length(content)
    if content_size + 3 > _A3_MAX_CONTENT:
        raise SceneParameterTooLargeError(
            f"Workshop content is {content_size + 3} bytes but the A3 line count only encodes {_A3_MAX_CONTENT}"
        )
    return _write(content, content_size)


def build_h6199_scene(scene_code: int, music_code: int = 0) -> bytes:
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.mode
    mode = _child(H6199CommandWrite.ModeBody, root)
    mode.sub_mode = H6199CommandWrite.ModeSel.scene
    detail = _child(H6199CommandWrite.SceneBody, mode)
    detail.scene_id = max(0, min(0xFFFF, scene_code))
    detail.music_code = max(0, min(0xFFFF, music_code))
    detail.reserved = bytes(12)
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)
