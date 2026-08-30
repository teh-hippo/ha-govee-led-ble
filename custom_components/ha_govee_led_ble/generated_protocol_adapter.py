"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from typing import Any, cast

from kaitaistruct import ConsistencyError, KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

from .const import get_profile
from .music_semantics import MusicVariant, music_variant
from .transport import A3_CHUNK_SIZE, xor_checksum

CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.command_write").CommandWrite,
)
H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
)
H6199CommandAck = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_ack").H6199CommandAck,
)
H6199EffectUpload = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_effect_upload").H6199EffectUpload,
)
StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.status_query").StatusQuery,
)
H6125BrightnessWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_brightness_write").H6125BrightnessWrite,
)
H6125ColourModeQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_colour_mode_query").H6125ColourModeQuery,
)
H6125StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_status_reply").H6125StatusReply,
)
H6125MusicWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_music_write").H6125MusicWrite,
)
H6199StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_query").H6199StatusQuery,
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
H6199StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_reply").H6199StatusReply,
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


@dataclass(frozen=True, slots=True)
class ProtocolParseResult:
    parsed: Any | None
    parser: str | None
    rejection: ProtocolParseRejection | None


DIY_PAINTED_EFFECTS = frozenset(DiyType03.Effect.__members__)

_BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS = 10
_BLANK_SCREEN_SAME_TONE_SECONDS = 120


def _check_tree(value: Any, seen: set[int] | None = None) -> None:
    seen = seen or set()
    if not isinstance(value, ReadWriteKaitaiStruct) or id(value) in seen:
        return
    seen.add(id(value))
    for name, child in vars(value).items():
        if name.startswith("_"):
            continue
        if isinstance(child, ReadWriteKaitaiStruct):
            _check_tree(child, seen)
        elif isinstance(child, list):
            for item in child:
                _check_tree(item, seen)
    value._check()


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
    return _SERIALIZE_MEASURE_BOUND


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
    "H6125": ("h6125_status_reply", H6125StatusReply),
    "H617A": ("status_reply", StatusReply),
    "H6199": ("h6199_status_reply", H6199StatusReply),
}
_COMMAND_ROOTS = {
    "H617A": ("command_write", CommandWrite),
    "H6199": ("h6199_command_write", H6199CommandWrite),
}
_COMMAND_ACK_ROOTS = {
    "H6199": ("h6199_command_ack", H6199CommandAck),
}


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
    except KaitaiStructError, UnicodeDecodeError:
        return ProtocolParseResult(None, parser, ProtocolParseRejection.SCHEMA_REJECTED)
    return ProtocolParseResult(parsed, parser, None)


def parse_status_result(frame: bytes, model: str = "H617A") -> ProtocolParseResult:
    return _parse_xor_frame(frame, get_profile(model).status_grammar, _STATUS_ROOTS)


def parse_status(frame: bytes, model: str = "H617A") -> Any | None:
    return parse_status_result(frame, model).parsed


def parse_command_result(frame: bytes, model: str = "H617A") -> ProtocolParseResult:
    return _parse_xor_frame(frame, get_profile(model).command_grammar, _COMMAND_ROOTS)


def parse_command_ack_result(frame: bytes, model: str) -> ProtocolParseResult:
    grammar = get_profile(model).video_grammar
    if grammar is None:
        return ProtocolParseResult(None, None, ProtocolParseRejection.UNSUPPORTED_MODEL)
    return _parse_xor_frame(frame, grammar, _COMMAND_ACK_ROOTS)


def parse_command(frame: bytes, model: str = "H617A") -> Any | None:
    return parse_command_result(frame, model).parsed


def parse_h6125_brightness_write(frame: bytes) -> Any | None:
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    try:
        parsed = H6125BrightnessWrite(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError:
        return None
    return parsed


def parse_h6125_music_write(frame: bytes) -> Any | None:
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    try:
        parsed = H6125MusicWrite(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError:
        return None
    return parsed


def parse_a3_effect_envelope(envelope: bytes, model: str) -> Any:
    """Parse one validated, padded A3 effect envelope through its generated root."""
    if not isinstance(envelope, bytes):
        raise TypeError("A3 effect envelope must be bytes")
    if len(envelope) < A3_CHUNK_SIZE or len(envelope) % A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope must contain complete 17-byte chunks")
    if envelope[0] != 0x01:
        raise ValueError("A3 effect envelope has an invalid marker")
    if envelope[1] != len(envelope) // A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope does not match its chunk count")

    grammar = get_profile(model).effect_grammar
    if grammar == "H617A":
        if model == "H6125" and envelope[2] not in {0x01, 0x02, 0x04}:
            raise ValueError(f"H6125 A3 body type 0x{envelope[2]:02x} is not supported")
        root_type = {
            0x01: SceneType1Body,
            0x02: SceneBody,
            0x03: DiyType03,
            0x04: DiyType04,
        }.get(envelope[2])
        if root_type is None:
            raise ValueError(f"H617A A3 body type 0x{envelope[2]:02x} is not supported")
    elif grammar == "H6199":
        root_type = H6199EffectUpload
    else:
        raise ValueError(f"{model} has no generated A3 effect grammar")

    try:
        parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
        parsed._read()
    except KaitaiStructError as error:
        raise ValueError(f"invalid {model} A3 effect envelope") from error
    if not parsed._io.is_eof():
        raise ValueError(f"{model} A3 effect grammar did not consume the envelope")
    return parsed


def _command_types(model: str) -> tuple[Any, Any, Any]:
    resolved = get_profile(model).command_grammar
    if resolved == "H6199":
        return (
            H6199CommandWrite,
            H6199CommandWrite.PowerBody,
            H6199CommandWrite.BrightnessBody,
        )
    if resolved != "H617A":
        raise ValueError(f"{model} has no generated command grammar")
    return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd


def new_child(struct_type: Any, parent: Any) -> Any:
    """Construct a read-write child struct bound to ``parent`` and its root."""
    return struct_type(None, parent, parent._root)


_child = new_child


def _build_status_query(
    domain: str,
    grammar: str | None,
    *,
    display_setting: str | None = None,
    segment_group: int | None = None,
) -> bytes:
    if grammar not in {"H617A", "H6199"}:
        raise ValueError(f"{grammar} has no generated status-query grammar")
    root_type = H6199StatusQuery if grammar == "H6199" else StatusQuery
    root = root_type()
    root.header = b"\xaa"
    root.domain = getattr(root_type.QueryDomain, domain)
    if display_setting is not None:
        body = _child(root_type.DisplaySettingQueryBody, root)
        body.setting = getattr(root_type.DisplaySetting, display_setting)
        body.zeros = [0] * 16
    elif segment_group is not None:
        body = _child(root_type.SegmentQueryBody, root)
        body.group = segment_group
        body.zeros = [0] * 16
    elif domain == "hardware":
        body = _child(root_type.HardwareQueryBody, root)
        body.selector = b"\x03"
        body.zeros = [0] * 16
    elif domain == "relative_brightness":
        body = _child(root_type.RelativeBrightnessQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    else:
        body = _child(root_type.ZeroBody, root)
        body.zeros = [0] * 17
    root.body = body
    return _serialize_xor(root)


def build_power_query(model: str = "H617A") -> bytes:
    return _build_status_query("power", get_profile(model).command_grammar)


def build_brightness_query(model: str = "H617A") -> bytes:
    return _build_status_query("brightness", get_profile(model).command_grammar)


def build_colour_mode_query(model: str = "H617A") -> bytes:
    if model == "H6125":
        root = H6125ColourModeQuery()
        root.header = b"\xaa\x05\x01"
        root.padding = b"\x00" * 16
        return _serialize_xor(root)
    return _build_status_query("colour_mode", get_profile(model).command_grammar)


def build_firmware_query(model: str = "H617A") -> bytes:
    return _build_status_query("firmware", get_profile(model).command_grammar)


def build_hardware_query(model: str = "H617A") -> bytes:
    return _build_status_query("hardware", get_profile(model).command_grammar)


def _video_grammar(model: str) -> str:
    profile = get_profile(model)
    if not profile.supports_video_mode or profile.video_grammar is None:
        raise ValueError(f"{model} does not support video mode")
    return profile.video_grammar


def build_white_balance_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_white_balance:
        raise ValueError(f"{model} does not support white balance")
    if _video_grammar(model) == "H6199":
        setting = "scalar_white_balance" if profile.video_white_balance_representation == "scalar" else "white_balance"
        return _build_status_query("display_setting", "H6199", display_setting=setting)
    raise ValueError(f"{model} has no generated white-balance query grammar")


def build_blank_screen_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_blank_screen:
        raise ValueError(f"{model} does not support blank-screen detection")
    if _video_grammar(model) == "H6199":
        return _build_status_query("display_setting", "H6199", display_setting="blank_screen")
    raise ValueError(f"{model} has no generated blank-screen query grammar")


def build_relative_brightness_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_relative_brightness:
        raise ValueError(f"{model} does not support relative brightness")
    if _video_grammar(model) == "H6199":
        return _build_status_query("relative_brightness", "H6199")
    raise ValueError(f"{model} has no generated relative-brightness query grammar")


def build_h6199_subordinate_query(domain: int) -> bytes:
    if domain not in {0x20, 0x21}:
        raise ValueError("H6199 subordinate query domain must be 0x20 or 0x21")
    return _build_status_query(f"subordinate_{domain:02x}", "H6199")


def build_segment_query(group: int, model: str = "H617A") -> bytes:
    resolved = get_profile(model).command_grammar
    if resolved not in {"H617A", "H6199"}:
        raise ValueError(f"{model} has no generated segment-query grammar")
    maximum = 4 if resolved == "H6199" else 5
    if not 1 <= group <= maximum:
        raise ValueError(f"segment query group must be from 1 to {maximum}")
    return _build_status_query("segments", resolved, segment_group=group)


def _rgb(parent: Any, red: int, green: int, blue: int) -> Any:
    colour = _child(GoveeShared.Rgb, parent)
    colour.red = max(0, min(255, red))
    colour.green = max(0, min(255, green))
    colour.blue = max(0, min(255, blue))
    return colour


def new_rgb(parent: Any, rgb: tuple[int, int, int]) -> Any:
    """Construct a shared RGB triple bound to ``parent`` from a colour tuple."""
    return _rgb(parent, *rgb)


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
    _check_tree(root)
    return _write(root, root.diy_chunk_count * A3_CHUNK_SIZE)


def _a3_header(parent: Any) -> Any:
    header = _child(GoveeCommon.A3Header, parent)
    header.marker = b"\x01"
    header.linecount = 2
    return header


def _parse_a3_scene(
    root_type: Any,
    scene_type_byte: int,
    raw_param: bytes,
    trailing_padding_of: Any,
) -> tuple[Any, int]:
    """Frame a stripped catalogue parameter and parse it through a generated A3 root.

    The parameter carries the real bytes only, so an unpadded read first measures the
    genuine trailing padding before the synthetic envelope padding a reassembled capture
    would carry is appended for the returned tree.
    """
    if not isinstance(raw_param, bytes):
        raise TypeError("scene parameter must be bytes")
    synthetic = root_type()
    header = _a3_header(synthetic)
    header_length = len(header.marker) + 1
    header.linecount = max(header.linecount, math.ceil((header_length + 1 + len(raw_param)) / A3_CHUNK_SIZE))
    _check_tree(header)
    header_bytes = _write(header, header_length)
    envelope = header_bytes + bytes((scene_type_byte,)) + raw_param
    unpadded = root_type(KaitaiStream(io.BytesIO(envelope)))
    unpadded._read()
    trailing_padding = len(trailing_padding_of(unpadded))
    envelope = envelope.ljust(header.linecount * A3_CHUNK_SIZE, b"\x00")
    parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
    parsed._read()
    return parsed, trailing_padding


def parse_scene_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse a catalogue type-2 parameter, returning its tree and real trailing padding."""
    return _parse_a3_scene(SceneBody, int(SceneBody.SceneType.scene_v2), raw_param, lambda root: root.padding)


def parse_scene_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-2 parameter through the generated SceneBody root."""
    return parse_scene_body(raw_param)[0]


def parse_workshop_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse an H617A Workshop parameter through the generated WorkshopBody root."""
    return _parse_a3_scene(WorkshopBody, 2, raw_param, lambda root: root.padding)


def parse_h6199_workshop_content(raw_param: bytes) -> tuple[Any, int]:
    """Parse an H6199 Workshop parameter through the generated effect-upload content."""
    if not isinstance(raw_param, bytes):
        raise TypeError("Workshop parameter must be bytes")
    root = H6199EffectUpload()
    parsed = H6199EffectUpload.SceneContent(KaitaiStream(io.BytesIO(raw_param)), root, root)
    parsed._read()
    return parsed, len(parsed.padding)


def parse_scene_type1_body(raw_param: bytes) -> tuple[Any, int]:
    """Parse a catalogue type-1 parameter, returning its tree and real trailing padding."""
    return _parse_a3_scene(SceneType1Body, 1, raw_param, lambda root: root.content.padding)


def parse_scene_type1_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-1 parameter through the generated SceneType1Body root."""
    return parse_scene_type1_body(raw_param)[0]


def serialize_scene_body_param(root: Any) -> bytes:
    """Serialize a built type-2 SceneBody root and return its catalogue parameter bytes."""
    _set_effect_layer_lengths(root.records)
    return _serialize_a3_scene_param(root)


def serialize_workshop_body_param(root: Any) -> bytes:
    """Serialize a built H617A WorkshopBody root and return its parameter bytes."""
    _set_effect_layer_lengths(root.layers)
    return _serialize_a3_scene_param(root)


def serialize_h6199_workshop_content(content: Any) -> bytes:
    """Serialize built H6199 Workshop content without its A3 envelope."""
    _set_effect_layer_lengths(content.blocks)
    _check_tree(content)
    content_size = _serialized_length(content)
    if content_size + 3 > _A3_MAX_CONTENT:
        raise SceneParameterTooLargeError(
            f"Workshop content is {content_size + 3} bytes but the A3 line count only encodes {_A3_MAX_CONTENT}"
        )
    return _write(content, content_size)


def _set_effect_layer_lengths(records: list[Any]) -> None:
    for record in records:
        _check_tree(record.body)
        body_length = _serialized_length(record.body)
        if body_length > _U1_MAX:
            raise SceneParameterTooLargeError(
                f"layer body is {body_length} bytes but the record length field only encodes {_U1_MAX}"
            )
        record.len_body = body_length


def serialize_scene_type1_body_param(root: Any) -> bytes:
    """Serialize a built type-1 SceneType1Body root and return its catalogue parameter bytes."""
    return _serialize_a3_scene_param(root)


def build_h617a_diy_painted_body(
    effect: str,
    speed: int,
    brightness: int,
    background: tuple[int, int, int],
    groups: list[tuple[tuple[int, int, int], list[int]]],
) -> bytes:
    """Serialize the diy_type03 fields after its A3 type byte."""
    root = DiyType03()
    root.header = _a3_header(root)
    root.body_type = b"\x03"
    root.effect = getattr(DiyType03.Effect, effect)
    root.speed = speed
    root.brightness = brightness
    root.background = _rgb(root, *background)
    root.num_groups = len(groups)
    root.groups = []
    for fill, segments in groups:
        group = _child(DiyType03.PaintGroup, root)
        group.num_segment_indices = len(segments)
        group.fill = _rgb(group, *fill)
        group.segment_indices = segments
        root.groups.append(group)
    root.padding = []
    length = 10 + sum(4 + len(segments) for _, segments in groups)
    _check_tree(root)
    return _write(root, length)[3:]


def _diy_type04_palette(parent: Any, colours: list[tuple[int, int, int]]) -> Any:
    palette = _child(DiyType04.Palette, parent)
    palette.colours = [_rgb(palette, *colour) for colour in colours]
    return palette


def build_h617a_diy_single_body(
    family: int,
    variant: int,
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Flat fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = family
    body = _child(DiyType04.FlatBody, root)
    body.variant = variant
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.padding = []
    root.body = body
    length = 7 + body.len_palette
    _check_tree(root)
    return _write(root, length)[3:]


def build_h617a_diy_multi_body(
    effects: list[tuple[int, int]],
    speed: int,
    palette: list[tuple[int, int, int]],
) -> bytes:
    """Serialize the diy_type04 Combo fields after the A3 type byte."""
    root = DiyType04()
    root.header = _a3_header(root)
    root.a3_type = b"\x04"
    root.family = 0xFF
    body = _child(DiyType04.ComboBody, root)
    body.variant = 0
    body.speed = speed
    body.len_palette = len(palette) * 3
    body.palette = _diy_type04_palette(body, palette)
    body.seqlen = len(effects) * 2
    body.pairs = []
    for family, variant in effects:
        pair = _child(DiyType04.FamilyVariant, body)
        pair.family = family
        pair.variant = variant
        body.pairs.append(pair)
    body.padding = []
    root.body = body
    length = 8 + body.len_palette + body.seqlen
    _check_tree(root)
    return _write(root, length)[3:]


def build_power(on: bool, model: str = "H617A") -> bytes:
    root_type, power_type, _ = _command_types(model)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.power
    body = power_type(None, root, root._root)
    body.is_on = int(on)
    root.body = body
    return _serialize_xor(root)


def build_brightness(percent: int, model: str = "H617A") -> bytes:
    root_type, _, brightness_type = _command_types(model)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.brightness
    body = brightness_type(None, root, root._root)
    body.percent = max(0, min(100, percent))
    root.body = body
    return _serialize_xor(root)


def build_h6125_brightness_value(value: int) -> bytes:
    root = H6125BrightnessWrite()
    root.header = b"\x33\x04"
    root.value = max(0, min(0xFF, value))
    root.padding = b"\x00" * 16
    return _serialize_xor(root)


def _build_h617a_static_colour(
    mask: int,
    *,
    direct: tuple[int, int, int],
    kelvin: int,
    preview: tuple[int, int, int],
) -> bytes:
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.static
    static = _child(CommandWrite.StaticCmd, multi)
    static.static_sub = 1
    colour = _child(CommandWrite.StaticColor, static)
    colour.rgb_direct = _rgb(colour, *direct)
    colour.kelvin = kelvin
    colour.rgb_preview = _rgb(colour, *preview)
    segment_mask = _child(CommandWrite.SegmentMask, colour)
    segment_mask.bits = mask
    colour.mask = segment_mask
    static.static_body = colour
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_segment_colour(
    mask: int,
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
) -> bytes:
    resolved = get_profile(model).command_grammar
    if resolved == "H6199":
        root = H6199CommandWrite()
        root.header = b"\x33"
        root.opcode = H6199CommandWrite.CommandOp.mode
        mode = _child(H6199CommandWrite.ModeBody, root)
        mode.sub_mode = H6199CommandWrite.ModeSel.static_colour
        detail = _child(H6199CommandWrite.StaticColourBody, mode)
        detail.operation = H6199CommandWrite.StaticOperation.colour
        detail.red = max(0, min(255, red))
        detail.green = max(0, min(255, green))
        detail.blue = max(0, min(255, blue))
        detail.kelvin = 0
        detail.preview = _rgb(detail, 0, 0, 0)
        detail.segment_mask = mask
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved != "H617A":
        raise ValueError(f"{model} has no generated static-colour grammar")
    return _build_h617a_static_colour(
        mask,
        direct=(red, green, blue),
        kelvin=0,
        preview=(0, 0, 0),
    )


def build_colour_temperature(
    kelvin: int,
    preview: tuple[int, int, int],
    mask: int,
    model: str = "H617A",
) -> bytes:
    value = max(2000, min(9000, kelvin))
    resolved = get_profile(model).command_grammar
    if resolved == "H6199":
        root = H6199CommandWrite()
        root.header = b"\x33"
        root.opcode = H6199CommandWrite.CommandOp.mode
        mode = _child(H6199CommandWrite.ModeBody, root)
        mode.sub_mode = H6199CommandWrite.ModeSel.static_colour
        detail = _child(H6199CommandWrite.StaticColourBody, mode)
        detail.operation = H6199CommandWrite.StaticOperation.colour
        detail.red = 0
        detail.green = 0
        detail.blue = 0
        detail.kelvin = value
        detail.preview = _rgb(detail, *preview)
        detail.segment_mask = mask
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved != "H617A":
        raise ValueError(f"{model} has no generated colour-temperature grammar")
    return _build_h617a_static_colour(
        mask,
        direct=(255, 255, 255) if model == "H6125" else (0, 0, 0),
        kelvin=value,
        preview=preview,
    )


def build_segment_brightness(
    mask: int,
    percent: int,
    model: str = "H617A",
) -> bytes:
    value = max(0, min(100, percent))
    resolved = get_profile(model).command_grammar
    if resolved == "H6199":
        root = H6199CommandWrite()
        root.header = b"\x33"
        root.opcode = H6199CommandWrite.CommandOp.mode
        mode = _child(H6199CommandWrite.ModeBody, root)
        mode.sub_mode = H6199CommandWrite.ModeSel.static_colour
        detail = _child(H6199CommandWrite.StaticColourBody, mode)
        detail.operation = H6199CommandWrite.StaticOperation.brightness
        detail.brightness_percent = value
        detail.brightness_segment_mask = mask
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved != "H617A":
        raise ValueError(f"{model} has no generated segment-brightness grammar")
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.static
    static = _child(CommandWrite.StaticCmd, multi)
    static.static_sub = 2
    brightness = _child(CommandWrite.StaticBrightness, static)
    brightness.percent = value
    segment_mask = _child(CommandWrite.SegmentMask, brightness)
    segment_mask.bits = mask
    brightness.mask = segment_mask
    static.static_body = brightness
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_scene_activation(
    model: str,
    scene_code: int,
    music_code: int = 0,
    *,
    scene_type: int = 0,
) -> bytes:
    """Encode a scene selector using only the target's evidenced command grammar."""
    grammar = get_profile(model).command_grammar
    if grammar == "H617A":
        return build_h617a_scene(scene_code, scene_type=scene_type)
    if grammar == "H6199":
        return build_h6199_scene(scene_code, music_code)
    raise ValueError(f"{model} has no generated scene activation grammar")


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


def build_h617a_scene(scene_code: int, *, scene_type: int = 0) -> bytes:
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.scene
    detail = _child(CommandWrite.SceneActivate, multi)
    detail.code = max(0, min(0xFFFF, scene_code))
    detail.scene_type = max(0, min(0xFF, scene_type))
    multi.sub_body = detail
    root.body = multi
    return _serialize_xor(root)


def build_h617a_diy_activation(diy_code: int) -> bytes:
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.diy
    selector = _child(GoveeCommon.DiySelector, multi)
    selector.code = diy_code
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def build_video_mode(
    video_mode: str,
    full_screen: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
    model: str,
) -> bytes:
    profile = get_profile(model)
    if video_mode not in profile.video_modes:
        raise ValueError(f"{model} does not support video mode {video_mode}")
    if _video_grammar(model) != "H6199":
        raise ValueError(f"{model} has no generated video-mode grammar")
    if video_mode not in {"movie", "game"}:
        raise ValueError(f"{model} video mode {video_mode} is not supported by the H6199 grammar")
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.mode
    mode = _child(H6199CommandWrite.ModeBody, root)
    mode.sub_mode = H6199CommandWrite.ModeSel.video
    detail = _child(H6199CommandWrite.VideoBody, mode)
    detail.region = H6199CommandWrite.VideoRegion.all if full_screen else H6199CommandWrite.VideoRegion.part
    detail.source = H6199CommandWrite.VideoSource.game if video_mode == "game" else H6199CommandWrite.VideoSource.movie
    detail.saturation = max(0, min(100, saturation))
    detail.sound_effects = int(sound_effects)
    detail.softness = max(1, min(100, softness))
    detail.relative_brightness_percent = 0
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def build_h6199_video(
    full_screen: bool,
    game_mode: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
) -> bytes:
    return build_video_mode("game" if game_mode else "movie", full_screen, saturation, sound_effects, softness, "H6199")


def build_white_balance(red: int, blue: int | None, model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_white_balance:
        raise ValueError(f"{model} does not support white balance")
    if _video_grammar(model) != "H6199":
        raise ValueError(f"{model} has no generated white-balance grammar")
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.display_setting
    body = _child(H6199CommandWrite.DisplaySettingBody, root)
    if profile.video_white_balance_representation == "scalar":
        if blue is not None or type(red) is not int or not 0 <= red <= 255:
            raise ValueError("scalar white balance requires one byte")
        body.setting = H6199CommandWrite.DisplaySetting.scalar_white_balance
        body.len = 1
        payload = _child(H6199CommandWrite.ScalarWhiteBalancePayload, body)
        payload.value = red
    else:
        if blue is None:
            raise ValueError("position white balance requires red and blue")
        body.setting = H6199CommandWrite.DisplaySetting.white_balance
        body.len = 3
        payload = _child(H6199CommandWrite.WhiteBalancePayload, body)
        payload.manual = 1
        payload.red = max(0, min(255, red))
        payload.blue = max(0, min(255, blue))
    body.payload = payload
    root.body = body
    return _serialize_xor(root)


def build_blank_screen(
    enabled: bool,
    model: str,
    detection: int = 2,
    low_brightness_duration_seconds: int = _BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS,
    same_tone_duration_seconds: int = _BLANK_SCREEN_SAME_TONE_SECONDS,
) -> bytes:
    profile = get_profile(model)
    if not profile.supports_blank_screen:
        raise ValueError(f"{model} does not support blank-screen detection")
    if _video_grammar(model) != "H6199":
        raise ValueError(f"{model} has no generated blank-screen grammar")
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.display_setting
    body = _child(H6199CommandWrite.DisplaySettingBody, root)
    body.setting = H6199CommandWrite.DisplaySetting.blank_screen
    body.len = 6
    payload = _child(H6199CommandWrite.BlankScreenPayload, body)
    payload.is_on = int(enabled)
    payload.detection = H6199CommandWrite.BlankScreenDetection(detection)
    payload.low_brightness_duration_seconds = max(0, min(0xFFFF, low_brightness_duration_seconds))
    payload.same_tone_duration_seconds = max(0, min(0xFFFF, same_tone_duration_seconds))
    body.payload = payload
    root.body = body
    return _serialize_xor(root)


def build_relative_brightness(
    left: int,
    top: int,
    right: int,
    bottom: int,
    model: str,
    strip_left: int | None = None,
    strip_right: int | None = None,
) -> bytes:
    profile = get_profile(model)
    if not profile.supports_relative_brightness:
        raise ValueError(f"{model} does not support relative brightness")
    if _video_grammar(model) != "H6199":
        raise ValueError(f"{model} has no generated relative-brightness grammar")
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.relative_brightness
    body = _child(H6199CommandWrite.RelativeBrightnessBody, root)
    body.selector = b"\x01"
    body.edge_count = len(profile.video_brightness_zones)
    if any((value is not None) != (body.edge_count == 6) for value in (strip_left, strip_right)):
        raise ValueError("brightness values must match the model topology")
    body.left_percent = max(0, min(100, left))
    body.top_percent = max(0, min(100, top))
    body.right_percent = max(0, min(100, right))
    body.bottom_percent = max(0, min(100, bottom))
    body.strip_left_percent = 0 if strip_left is None else max(0, min(100, strip_left))
    body.strip_right_percent = 0 if strip_right is None else max(0, min(100, strip_right))
    root.body = body
    return _serialize_xor(root)


def build_music_mode(
    mode_id: int,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    model: str = "H617A",
) -> bytes:
    from .const import music_mode_code

    profile = get_profile(model)
    if type(mode_id) is not int or mode_id not in (music_mode_code(model, slug) for slug in profile.music_modes):
        raise ValueError(f"{model} does not support music mode {mode_id}")
    if (
        type(sensitivity) is not int
        or not profile.music_sensitivity_min <= sensitivity <= profile.music_sensitivity_max
    ):
        raise ValueError("music sensitivity is outside model limits")
    variant = music_variant(profile, mode_id)
    if not isinstance(calm, bool) or (calm and (variant is None or not variant.supports_style)):
        raise ValueError("music style is unsupported or invalid")
    if colour is not None and (
        not profile.supports_music_color
        or model == "H6125"
        and mode_id not in {0x11, 0x12, 0x13}
        or len(colour) != 3
        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in colour)
    ):
        raise ValueError("fixed music colour is unsupported or invalid")
    resolved = profile.command_grammar
    if model == "H6125":
        root = H6125MusicWrite()
        root.header = b"\x33\x05\x11"
        root.mode = H6125MusicWrite.MusicMode(mode_id)
        root.sensitivity = max(0, min(99, sensitivity))
        if mode_id == 0x11:
            settings = _child(H6125MusicWrite.RhythmSettings, root)
            settings.style = int(calm)
            settings.manual_colour = int(colour is not None)
            if colour is not None:
                settings.rgb = _rgb(settings, *colour)
            settings.padding = bytes(9 if colour is not None else 12)
        elif mode_id in {0x12, 0x13}:
            settings = _child(H6125MusicWrite.ColourSettings, root)
            settings.manual_colour = int(colour is not None)
            if colour is not None:
                settings.rgb = _rgb(settings, *colour)
            settings.padding = bytes(10 if colour is not None else 13)
        else:
            settings = _child(H6125MusicWrite.EmptySettings, root)
            settings.padding = bytes(14)
        root.settings = settings
        return _serialize_xor(root)
    if resolved == "H6199":
        root = H6199CommandWrite()
        root.header = b"\x33"
        root.opcode = H6199CommandWrite.CommandOp.mode
        mode = _child(H6199CommandWrite.ModeBody, root)
        mode.sub_mode = H6199CommandWrite.ModeSel.music
        detail = _child(H6199CommandWrite.MusicBody, mode)
        detail.mode = H6199CommandWrite.MusicMode(mode_id)
        detail.sensitivity = max(0, min(100, sensitivity))
        detail.is_calm = int(calm)
        detail.has_fixed_colour = int(colour is not None)
        detail.fixed_colour = _rgb(detail, *(colour or (0, 0, 0)))
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    if resolved != "H617A":
        raise ValueError(f"{model} has no generated music grammar")
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.music
    selector = _child(GoveeCommon.MusicSelector, multi)
    selector.mode_id = GoveeCommon.MusicMode(mode_id)
    selector.sensitivity = max(0, min(100, sensitivity))
    selector.style = int(calm)
    selector.manual_color_count = int(colour is not None)
    if colour is not None:
        selector.rgb = _rgb(selector, *colour)
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def encode_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    *,
    palette: list[tuple[int, int, int]] | None,
    calm: bool,
) -> bytes:
    """Edit named Kaitai fields; palette length never becomes an absolute tail offset."""
    if variant.layout != "music_body" or not variant.evidence or not variant.template:
        raise ValueError("music parameter layout is unqualified")
    root = MusicBody.from_bytes(b"\x01\x02\x41" + variant.template)
    root._read()
    if root.mode != variant.mode_code:
        raise ValueError("music template does not match variant mode")
    if palette is not None:
        if len(palette) != root.num_palette:
            raise ValueError("palette count does not match music variant")
        if any(
            len(rgb) != 3 or any(type(channel) is not int or not 0 <= channel <= 255 for channel in rgb)
            for rgb in palette
        ):
            raise ValueError("invalid music palette")
        root.palette = [_rgb(root, *rgb) for rgb in palette]
    tail = root.tail
    for spec in variant.parameters:
        value = parameters[spec.profile_key]
        if not hasattr(tail, spec.wire_field):
            raise ValueError("music parameter field is absent from qualified layout")
        if spec.kind != "select":
            setattr(tail, spec.wire_field, int(value))
    if variant.gradient_companions is not None:
        tail.companion = variant.gradient_companions[bool(parameters["gradient"])]
    if variant.piano_derived_half:
        tail.derived_half = tail.key_count // 2
    if variant.direction_values:
        tail.start_point, tail.piece_num = {name: (start, pieces) for name, start, pieces in variant.direction_values}[
            str(parameters["direction"])
        ]
    if variant.style_companions is not None:
        value = variant.style_companions[calm]
        tail.style_companion = MusicBody.ShinyStyle(value) if isinstance(tail, MusicBody.ShinyTail) else value
    _check_tree(root)
    return _write(root, len(variant.template) + 3)[3:]
