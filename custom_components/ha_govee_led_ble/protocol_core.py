"""Kaitai root types and the framing helpers shared by every grammar adapter."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from typing import Any, cast

from kaitaistruct import ConsistencyError, KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

from .transport import (
    A3_CHUNK_SIZE,
    xor_checksum,
)

CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.command_write").CommandWrite,
)


H6099CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_command_write").H6099CommandWrite,
)


H6099StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_status_query").H6099StatusQuery,
)


H6099StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_status_reply").H6099StatusReply,
)


H6099EffectUpload = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_effect_upload").H6099EffectUpload,
)


H6099CommandAck = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6099_command_ack").H6099CommandAck,
)


H617aCommandAck = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h617a_command_ack").H617aCommandAck,
)


H617aControlPayload = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h617a_control_payload").H617aControlPayload,
)


H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
)


H6199Pact1WireWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_pact1_wire_write").H6199Pact1WireWrite,
)


H6179CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write").H6179CommandWrite,
)


H6179DiyBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_diy_body").H6179DiyBody,
)


H6199CommandAck = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_ack").H6199CommandAck,
)


H6199ControlPayload = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_control_payload").H6199ControlPayload,
)


H6199EffectUpload = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_effect_upload").H6199EffectUpload,
)


StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.status_query").StatusQuery,
)


H6199StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_query").H6199StatusQuery,
)


H6179StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_status_query").H6179StatusQuery,
)


GoveeShared = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.govee_shared").GoveeShared,
)


GoveeCommon = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.govee_common").GoveeCommon,
)


StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.status_reply").StatusReply,
)


H6102WireWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6102_wire_write").H6102WireWrite,
)


H66a0StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h66a0_status_reply").H66a0StatusReply,
)


H6199StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_reply").H6199StatusReply,
)


H6179StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_status_reply").H6179StatusReply,
)


H7020CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7020_command_write").H7020CommandWrite,
)


H7020StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7020_status_query").H7020StatusQuery,
)


H7020StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h7020_status_reply").H7020StatusReply,
)


H6102StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6102_status_reply").H6102StatusReply,
)


H617cStatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h617c_status_reply").H617cStatusReply,
)


H601cCommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h601c_command_write").H601cCommandWrite,
)


H601cStatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h601c_status_reply").H601cStatusReply,
)


H60a1StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a1_status_reply").H60a1StatusReply,
)


H60a6StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_status_reply").H60a6StatusReply,
)


H60aBulk = cast(Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a_bulk").H60aBulk)


H60a6Control = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_control").H60a6Control
)


H60a6LegacyWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_legacy_write").H60a6LegacyWrite
)


H60a6EffectFrame = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_effect_frame").H60a6EffectFrame
)


H60a6CommandAck = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_command_ack").H60a6CommandAck
)


H60a6DiyBody = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_diy_body").H60a6DiyBody
)


H60a6PaintBody = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h60a6_paint_body").H60a6PaintBody
)


DiyType03 = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.diy_type03").DiyType03,
)


DiyType04 = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.diy_type04").DiyType04,
)


SceneBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.scene_body").SceneBody,
)


SceneType1Body = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.scene_type1_body").SceneType1Body,
)


WorkshopBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.workshop_body").WorkshopBody,
)


MusicBody = cast(Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.music_body").MusicBody)


H6076MusicAck = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_ack").H6076MusicAck
)


H6076MusicBody = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_body").H6076MusicBody
)


H6076MusicWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_music_write").H6076MusicWrite
)


H6076StatusReply = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h6076_status_reply").H6076StatusReply
)


H7025MusicBody = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h7025_music_body").H7025MusicBody
)


H7025MusicWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h7025_music_write").H7025MusicWrite
)


H66a0MusicWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h66a0_music_write").H66a0MusicWrite
)


H1a42MusicWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h1a42_music_write").H1a42MusicWrite
)


H1a42StatusReply = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h1a42_status_reply").H1a42StatusReply
)


H61f5MusicWrite = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h61f5_music_write").H61f5MusicWrite
)


H61f5StatusReply = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h61f5_status_reply").H61f5StatusReply
)


H7025StatusReply = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h7025_status_reply").H7025StatusReply
)


H6125StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_status_reply").H6125StatusReply,
)


H6125ModernStatusReply = cast(
    Any,
    import_module(
        "custom_components.ha_govee_led_ble.generated_protocol.h6125_modern_status_reply"
    ).H6125ModernStatusReply,
)


H6125IntermediateStatusReply = cast(
    Any,
    import_module(
        "custom_components.ha_govee_led_ble.generated_protocol.h6125_intermediate_status_reply"
    ).H6125IntermediateStatusReply,
)


H6125CommandAck = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_command_ack").H6125CommandAck,
)


H6125LegacyStatusReply = cast(
    Any,
    import_module(
        "custom_components.ha_govee_led_ble.generated_protocol.h6125_legacy_status_reply"
    ).H6125LegacyStatusReply,
)


H6125LegacySegmentQuery = cast(
    Any,
    import_module(
        "custom_components.ha_govee_led_ble.generated_protocol.h6125_legacy_segment_query"
    ).H6125LegacySegmentQuery,
)


H6125WireWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_wire_write").H6125WireWrite,
)


H66a0VideoCommand = cast(
    Any, import_module("custom_components.ha_govee_led_ble.generated_protocol.h66a0_video_command").H66a0VideoCommand
)


_U1_MAX = 0xFF


_A3_MAX_CONTENT = _U1_MAX * A3_CHUNK_SIZE


# The A3 line count is a u1, so a framed scene parameter spans at most 255 lines of 17 bytes.
MAX_SCENE_PARAM_BYTES = _A3_MAX_CONTENT


class SceneParameterTooLargeError(ValueError):
    """A built scene exceeds the byte limits the generated A3 fields can encode."""


class ProtocolParseRejection(StrEnum):
    INVALID_LENGTH = "invalid_length"
    INVALID_CHECKSUM = "invalid_checksum"
    UNSUPPORTED_MODEL = "unsupported_model"
    SCHEMA_REJECTED = "schema_rejected"
    SEMANTIC_REJECTED = "semantic_rejected"


@dataclass(frozen=True, slots=True)
class ProtocolParseResult:
    parsed: Any | None
    parser: str | None
    rejection: ProtocolParseRejection | None


DIY_PAINTED_EFFECTS = frozenset(DiyType03.Effect.__members__)


_BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS = 10


_BLANK_SCREEN_SAME_TONE_SECONDS = 120


def check_generated_tree(value: Any, seen: set[int] | None = None) -> None:
    seen = seen or set()
    if not isinstance(value, ReadWriteKaitaiStruct) or id(value) in seen:
        return
    seen.add(id(value))
    for name, child in tuple(vars(value).items()):
        if name.startswith("_"):
            continue
        if isinstance(child, ReadWriteKaitaiStruct):
            check_generated_tree(child, seen)
        elif isinstance(child, list):
            for item in child:
                check_generated_tree(item, seen)
    value._check()


_check_tree = check_generated_tree


def _write(value: ReadWriteKaitaiStruct, length: int) -> bytes:
    stream = KaitaiStream(io.BytesIO(bytes(length)))
    value._write(stream)
    return cast(bytes, stream.to_byte_array())


_SERIALIZE_MEASURE_BOUND = 1 << 16


def _serialized_length(value: ReadWriteKaitaiStruct) -> int:
    """Return the serialized length of a checked struct from the generated writer.

    Kaitai's writer needs a pre-sized buffer, so an oversized write is measured by the
    trailing ``size-eos`` consistency check, whose ``actual`` is the unused byte count.
    """
    try:
        _write(value, _SERIALIZE_MEASURE_BOUND)
    except ConsistencyError as error:
        return _SERIALIZE_MEASURE_BOUND - int(error.actual)
    return cast(int, value._io.pos())


def serialize_native_body(root: Any) -> bytes:
    """Write a complete native body, retaining its generated lengths and opaque fields."""
    _check_tree(root)
    length = _serialized_length(root)
    if not 0 < length <= _SERIALIZE_MEASURE_BOUND:
        raise ValueError("Native effect body exceeds the serialization bound")
    return _write(root, length)


def _serialize_a3_scene_param(root: Any, *, scene_type_size: int = 1) -> bytes:
    """Frame a built A3 scene root and return its parameter bytes without envelope padding.

    ``linecount`` only sits in the stripped header, so the parameter is independent of it;
    it is still set to the value a reassembled capture would carry.
    """
    root.header = _a3_header(root)
    _check_tree(root)
    content_size = _serialized_length(root)
    if content_size > _A3_MAX_CONTENT:
        raise SceneParameterTooLargeError(
            f"scene content is {content_size} bytes but the A3 line count only encodes {_A3_MAX_CONTENT}"
        )
    root.header.linecount = max(2, math.ceil(content_size / A3_CHUNK_SIZE))
    _check_tree(root)
    envelope = _write(root, content_size)
    return envelope[len(root.header.marker) + 1 + scene_type_size :]


def _serialize_xor(root: Any, length: int = 20) -> bytes:
    root.checksum = 0
    _check_tree(root)
    provisional = _write(root, length)
    root.checksum = xor_checksum(provisional[:-1])
    _check_tree(root)
    return _write(root, length)


_STATUS_ROOTS = {
    "H60A1": ("h60a1_status_reply", H60a1StatusReply),
    "H60A6": ("h60a6_status_reply", H60a6StatusReply),
    "H601C": ("h601c_status_reply", H601cStatusReply),
    "H6076": ("h6076_status_reply", H6076StatusReply),
    "H6102": ("h6102_status_reply", H6102StatusReply),
    "H6125": ("h6125_status_reply", H6125StatusReply),
    "H6125-modern": ("h6125_modern_status_reply", H6125ModernStatusReply),
    "H6125-legacy": ("h6125_legacy_status_reply", H6125LegacyStatusReply),
    "H6125-intermediate": ("h6125_intermediate_status_reply", H6125IntermediateStatusReply),
    "H6099": ("h6099_status_reply", H6099StatusReply),
    "H66A0": ("h66a0_status_reply", H66a0StatusReply),
    "H1A42": ("h1a42_status_reply", H1a42StatusReply),
    "H61F5": ("h61f5_status_reply", H61f5StatusReply),
    "H617A": ("status_reply", StatusReply),
    "H617C": ("h617c_status_reply", H617cStatusReply),
    "H7025": ("h7025_status_reply", H7025StatusReply),
    "H6179": ("h6179_status_reply", H6179StatusReply),
    "H6199": ("h6199_status_reply", H6199StatusReply),
    "H7020": ("h7020_status_reply", H7020StatusReply),
}


_COMMAND_ROOTS = {
    "H601C": ("h601c_command_write", H601cCommandWrite),
    "H6099": ("h6099_command_write", H6099CommandWrite),
    "H617A": ("command_write", CommandWrite),
    "H6179": ("h6179_command_write", H6179CommandWrite),
    "H6199": ("h6199_command_write", H6199CommandWrite),
    "H7020": ("h7020_command_write", H7020CommandWrite),
}


_STATUS_QUERY_ROOTS = {
    "H601C": ("status_query", StatusQuery),
    "H6099": ("h6099_status_query", H6099StatusQuery),
    "H617A": ("status_query", StatusQuery),
    "H6179": ("h6179_status_query", H6179StatusQuery),
    "H6199": ("h6199_status_query", H6199StatusQuery),
    "H7020": ("h7020_status_query", H7020StatusQuery),
}


_H6076_ACK_ROOTS = {"H6076": ("h6076_music_ack", H6076MusicAck)}


_MUSIC_WRITE_ROOTS = {
    "H6076": ("h6076_music_write", H6076MusicWrite),
    "H66A0": ("h66a0_music_write", H66a0MusicWrite),
    "H1A42": ("h1a42_music_write", H1a42MusicWrite),
    "H61F5": ("h61f5_music_write", H61f5MusicWrite),
    "H7025": ("h7025_music_write", H7025MusicWrite),
}


_COMMAND_ACK_ROOTS = {
    "H60A6": ("h60a6_command_ack", H60a6CommandAck),
    "H6125": ("h6125_command_ack", H6125CommandAck),
    "H6099": ("h6099_command_ack", H6099CommandAck),
    "H617A": ("h617a_command_ack", H617aCommandAck),
    "H6199": ("h6199_command_ack", H6199CommandAck),
    "H7020": ("h617a_command_ack", H617aCommandAck),
}


def _has_unknown_discriminator(parsed: Any, parser: str) -> bool:
    if getattr(parsed.opcode, "name", None) is None:
        return True
    if parser in {"command_write", "h7020_command_write"} and parsed.opcode.name == "multi":
        sub = getattr(parsed.body.sub, "name", None)
        return (
            sub is None
            or (parser == "h7020_command_write" and sub == "static" and not parsed.is_static)
            or (
                parser == "h7020_command_write"
                and sub == "music"
                and getattr(parsed.body.sub_body.mode_id, "name", None) is None
            )
        )
    if parser == "h6199_command_write" and parsed.opcode.name == "mode":
        mode = getattr(parsed.body.sub_mode, "name", None)
        return mode is None or (mode == "static_colour" and getattr(parsed.body.detail.operation, "name", None) is None)
    return False


def _parse_xor_frame(
    frame: bytes,
    grammar: str | None,
    roots: dict[str, tuple[str, Any]],
) -> ProtocolParseResult:
    if len(frame) != 20:
        return ProtocolParseResult(None, None, ProtocolParseRejection.INVALID_LENGTH)
    if xor_checksum(frame[:-1]) != frame[-1]:
        return ProtocolParseResult(None, None, ProtocolParseRejection.INVALID_CHECKSUM)
    if grammar is None:
        return ProtocolParseResult(None, None, ProtocolParseRejection.UNSUPPORTED_MODEL)
    root = roots.get(grammar)
    if root is None:
        return ProtocolParseResult(None, None, ProtocolParseRejection.UNSUPPORTED_MODEL)
    parser, root_type = root
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError, UnicodeDecodeError, EOFError:
        return ProtocolParseResult(None, parser, ProtocolParseRejection.SCHEMA_REJECTED)
    return ProtocolParseResult(parsed, parser, None)


def new_child(struct_type: Any, parent: Any) -> Any:
    """Construct a read-write child struct bound to ``parent`` and its root."""
    return struct_type(None, parent, parent._root)


_child = new_child


def _rgb(parent: Any, red: int, green: int, blue: int) -> Any:
    colour = _child(GoveeShared.Rgb, parent)
    colour.red = max(0, min(255, red))
    colour.green = max(0, min(255, green))
    colour.blue = max(0, min(255, blue))
    return colour


def new_rgb(parent: Any, rgb: tuple[int, int, int]) -> Any:
    """Construct a shared RGB triple bound to ``parent`` from a colour tuple."""
    return _rgb(parent, *rgb)


def _a3_header(parent: Any) -> Any:
    header = _child(GoveeCommon.A3Header, parent)
    header.marker = b"\x01"
    header.linecount = 2
    return header


def _set_effect_layer_lengths(records: list[Any]) -> None:
    for record in records:
        check_generated_tree(record.body)
        body_length = _serialized_length(record.body)
        if body_length > _U1_MAX:
            raise SceneParameterTooLargeError(
                f"layer body is {body_length} bytes but the record length field only encodes {_U1_MAX}"
            )
        record.len_body = body_length


def encode_wire_brightness(percent: int, wire_range: tuple[int, int]) -> int:
    """Map a 1..100 percentage onto a device register range with the app's linear rule."""
    if not isinstance(percent, int) or isinstance(percent, bool) or not 1 <= percent <= 100:
        raise ValueError("brightness must be an integer from 1 to 100")
    low, high = wire_range
    return (low * 100 + (percent - 1) * (high - low + 3)) // 100


def decode_wire_brightness(raw: int, wire_range: tuple[int, int] | None) -> int:
    """Invert encode_wire_brightness; clamp non-zero unsigned bytes to the declared range."""
    if wire_range is None:
        raise ValueError("brightness register range is not declared")
    low, high = wire_range
    if not isinstance(raw, int) or isinstance(raw, bool) or not 1 <= raw <= 255:
        raise ValueError(f"brightness register must be an integer from {low} to {high}")
    clamped = min(max(raw, low), high)
    return max(1, min(100, 1 - (-((clamped - low) * 100) // (high - low + 3))))
