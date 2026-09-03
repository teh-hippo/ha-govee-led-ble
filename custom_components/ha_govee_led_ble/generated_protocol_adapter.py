"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib import import_module
from types import MappingProxyType
from typing import Any, cast

from kaitaistruct import ConsistencyError, KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

from .const import get_profile, protocol_model, wire_model
from .music_protocol import music_slug_for
from .transport import A3_CHUNK_SIZE, xor_checksum

CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.command_write").CommandWrite,
)
H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
)
H6179CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write").H6179CommandWrite,
)
H6179DiyBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_diy_body").H6179DiyBody,
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
H6199StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_reply").H6199StatusReply,
)
H6179StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_status_reply").H6179StatusReply,
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


@dataclass(frozen=True, slots=True)
class WireProtocolCodec:
    """Generated roots and supported query names for one wire family."""

    command_write: Any
    status_query: Any
    status_reply: Any
    query_domains: Mapping[str, str | int]
    diy_body: Any | None = None


WIRE_PROTOCOL_CODECS: Mapping[str, WireProtocolCodec] = MappingProxyType(
    {
        "H617A": WireProtocolCodec(
            command_write=CommandWrite,
            status_query=StatusQuery,
            status_reply=StatusReply,
            query_domains=MappingProxyType(
                {
                    "power": "power",
                    "brightness": "brightness",
                    "colour_mode": "colour_mode",
                    "firmware": "firmware",
                    "hardware": "hardware",
                    "segments": "segments",
                }
            ),
        ),
        "H6179": WireProtocolCodec(
            command_write=H6179CommandWrite,
            status_query=H6179StatusQuery,
            status_reply=H6179StatusReply,
            diy_body=H6179DiyBody,
            query_domains=MappingProxyType(
                {
                    "power": "power",
                    "brightness": "brightness",
                    "mode": "mode",
                    "colour_mode": "mode",
                    "firmware": "firmware",
                    "hardware": "hardware",
                }
            ),
        ),
        "H6199": WireProtocolCodec(
            command_write=H6199CommandWrite,
            status_query=H6199StatusQuery,
            status_reply=H6199StatusReply,
            query_domains=MappingProxyType(
                {
                    "power": "power",
                    "brightness": "brightness",
                    "colour_mode": "colour_mode",
                    "firmware": "firmware",
                    "hardware": "hardware",
                    "subordinate_20": "subordinate_20",
                    "subordinate_21": "subordinate_21",
                    "segments": "segments",
                    "display_setting": "display_setting",
                    "relative_brightness": "relative_brightness",
                }
            ),
        ),
    }
)


def _codec_for(model: str, operation: str) -> WireProtocolCodec:
    resolved = wire_model(model)
    if resolved is None or (codec := WIRE_PROTOCOL_CODECS.get(resolved)) is None:
        raise ValueError(f"{model} has no {operation} codec")
    return codec


@dataclass(frozen=True, slots=True)
class ParsedH6179Command:
    operation: str
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedH6179Status:
    domain: str
    values: Mapping[str, Any]


def _values(**values: Any) -> Mapping[str, Any]:
    return MappingProxyType(values)


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
    for name, child in vars(value).items():
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
    return _SERIALIZE_MEASURE_BOUND


def _serialize_a3_scene_param(root: Any, *, scene_type_size: int = 1) -> bytes:
    """Frame a built A3 scene root and return its parameter bytes without envelope padding.

    ``linecount`` only sits in the stripped header, so the parameter is independent of it;
    it is still set to the value a reassembled capture would carry.
    """
    root.header = _a3_header(root)
    check_generated_tree(root)
    content_size = _serialized_length(root)
    if content_size > _A3_MAX_CONTENT:
        raise SceneParameterTooLargeError(
            f"scene content is {content_size} bytes but the A3 line count only encodes {_A3_MAX_CONTENT}"
        )
    root.header.linecount = max(2, math.ceil(content_size / A3_CHUNK_SIZE))
    check_generated_tree(root)
    envelope = _write(root, content_size)
    return envelope[len(root.header.marker) + 1 + scene_type_size :]


def _serialize_xor(root: Any, length: int = 20) -> bytes:
    root.checksum = 0
    check_generated_tree(root)
    provisional = _write(root, length)
    root.checksum = xor_checksum(provisional[:-1])
    check_generated_tree(root)
    return _write(root, length)


_STATUS_ROOTS = {
    "H617A": ("status_reply", StatusReply),
    "H6179": ("speculative/h6179_status_reply", H6179StatusReply),
    "H6199": ("h6199_status_reply", H6199StatusReply),
}
_COMMAND_ROOTS = {
    "H617A": ("command_write", CommandWrite),
    "H6179": ("speculative/h6179_command_write", H6179CommandWrite),
    "H6199": ("h6199_command_write", H6199CommandWrite),
}


def _has_unknown_discriminator(parsed: Any, parser: str) -> bool:
    if parser.startswith("speculative/h6179_"):
        return False
    if parser.endswith("status_reply"):
        return getattr(parsed.domain, "name", None) is None
    if getattr(parsed.opcode, "name", None) is None:
        return True
    if parser == "command_write" and parsed.opcode.name == "multi":
        return getattr(parsed.body.sub, "name", None) is None
    if parser == "h6199_command_write" and parsed.opcode.name == "mode":
        return getattr(parsed.body.sub_mode, "name", None) is None
    return False


def _parse_xor_frame(
    frame: bytes,
    model: str,
    roots: dict[str, tuple[str, Any]],
) -> ProtocolParseResult:
    if len(frame) != 20:
        return ProtocolParseResult(None, None, ProtocolParseRejection.INVALID_LENGTH)
    if xor_checksum(frame[:-1]) != frame[-1]:
        return ProtocolParseResult(None, None, ProtocolParseRejection.INVALID_CHECKSUM)
    resolved = wire_model(model)
    if resolved is None:
        return ProtocolParseResult(None, None, ProtocolParseRejection.UNSUPPORTED_MODEL)
    root = roots.get(resolved)
    if root is None:
        return ProtocolParseResult(None, None, ProtocolParseRejection.UNSUPPORTED_MODEL)
    parser, root_type = root
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError, UnicodeDecodeError:
        return ProtocolParseResult(None, parser, ProtocolParseRejection.SCHEMA_REJECTED)
    if _has_unknown_discriminator(parsed, parser):
        return ProtocolParseResult(None, parser, ProtocolParseRejection.SEMANTIC_REJECTED)
    return ProtocolParseResult(parsed, parser, None)


def parse_status_result(frame: bytes, model: str = "H617A") -> ProtocolParseResult:
    return _parse_xor_frame(frame, model, _STATUS_ROOTS)


def parse_status(frame: bytes, model: str = "H617A") -> Any | None:
    return parse_status_result(frame, model).parsed


def parse_command_result(frame: bytes, model: str = "H617A") -> ProtocolParseResult:
    return _parse_xor_frame(frame, model, _COMMAND_ROOTS)


def parse_command(frame: bytes, model: str = "H617A") -> Any | None:
    return parse_command_result(frame, model).parsed


def parse_status_query(frame: bytes, model: str = "H617A") -> Any | None:
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    try:
        root_type = _codec_for(model, "status-query").status_query
        parsed = root_type(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except ValueError, KaitaiStructError, UnicodeDecodeError:
        return None
    return parsed


def _has_zero_opaque(body: Any) -> bool:
    return not any(body.opaque)


def _h6179_mode_values(body: Any, *, command: bool) -> Mapping[str, Any] | None:
    mode = getattr(body.mode, "name", None)
    if mode is None:
        return None
    detail = body.payload if command else body.detail
    profile = get_profile("H6179")
    if not _has_zero_opaque(detail):
        return None
    if mode == "static":
        direct = detail.rgb_direct if command else detail.colour
        preview = detail.rgb_preview if command else detail.temperature_colour
        kelvin = int(detail.kelvin)
        if kelvin and not profile.min_color_temp_kelvin <= kelvin <= profile.max_color_temp_kelvin:
            return None
        return _values(
            mode=mode,
            raw_mode=int(body.mode),
            rgb=(int(direct.red), int(direct.green), int(direct.blue)),
            kelvin=kelvin,
            preview_rgb=(int(preview.red), int(preview.green), int(preview.blue)),
        )
    if mode == "scene":
        return _values(mode=mode, raw_mode=int(body.mode), scene_code=int(detail.scene_id))
    if mode == "diy":
        return _values(mode=mode, raw_mode=int(body.mode), diy_code=int(detail.diy_id))
    if mode == "music":
        mode_id = int(detail.effect_id if command else detail.music_id)
        if (
            music_slug_for("H6179", mode_id) is None
            or not profile.music_sensitivity_min <= int(detail.sensitivity) <= profile.music_sensitivity_max
        ):
            return None
        if detail.colour_mode not in {0, 1}:
            return None
        automatic = detail.colour_mode == 0
        colour = None
        if not automatic:
            colour = (
                int(detail.fixed_colour.red),
                int(detail.fixed_colour.green),
                int(detail.fixed_colour.blue),
            )
        return _values(
            mode=mode,
            raw_mode=int(body.mode),
            music_mode=music_slug_for("H6179", mode_id),
            music_mode_id=mode_id,
            sensitivity=int(detail.sensitivity),
            colour=colour,
        )
    return None


def parse_h6179_command(frame: bytes) -> ParsedH6179Command | None:
    """Parse an H6179 command into semantic values without exposing generated classes."""
    parsed = parse_command(frame, "H6179")
    if parsed is None:
        return None
    operation = getattr(parsed.opcode, "name", None)
    if operation == "power":
        if parsed.body.is_on not in {0, 1} or not _has_zero_opaque(parsed.body):
            return None
        values = _values(is_on=bool(parsed.body.is_on))
    elif operation == "brightness":
        if not _has_zero_opaque(parsed.body):
            return None
        try:
            brightness_pct = decode_h6179_brightness(int(parsed.body.raw))
        except ValueError:
            return None
        values = _values(brightness_pct=brightness_pct)
    elif operation == "mode":
        mode_values = _h6179_mode_values(parsed.body, command=True)
        if mode_values is None:
            return None
        values = mode_values
    else:
        return None
    return ParsedH6179Command(operation=operation, values=values)


def parse_h6179_status_query(frame: bytes) -> str | None:
    """Return the semantic H6179 domain selected by a valid status query."""
    parsed = parse_status_query(frame, "H6179")
    if parsed is None:
        return None
    domain = getattr(parsed.domain, "name", None)
    if domain is None or not _has_zero_opaque(parsed.body):
        return None
    if domain == "mode" and getattr(parsed.body.selector, "name", None) != "current":
        return None
    if domain == "hardware" and getattr(parsed.body.selector, "name", None) != "primary":
        return None
    return cast(str, domain)


def _parse_h6179_status(parsed: Any) -> ParsedH6179Status | None:
    domain = getattr(parsed.domain, "name", None)
    if domain is None:
        return None
    body = parsed.body
    if domain != "mode" and not _has_zero_opaque(body):
        return None
    if domain == "power":
        if body.state not in {0, 1}:
            return None
        values = _values(is_on=bool(body.is_on))
    elif domain == "brightness":
        values = _values(brightness_pct=decode_h6179_brightness(int(body.raw_brightness)))
    elif domain in {"firmware", "hardware"}:
        if domain == "hardware" and getattr(body.selector, "name", None) != "primary":
            return None
        values = _values(version=body.text or None)
    elif domain == "mode":
        mode_values = _h6179_mode_values(body, command=False)
        if mode_values is None:
            return None
        values = mode_values
    else:
        return None
    return ParsedH6179Status(domain=domain, values=values)


def parse_h6179_status_result(frame: bytes) -> ProtocolParseResult:
    """Parse an H6179 reply into stable semantic fields and preserve rejection detail."""
    result = parse_status_result(frame, "H6179")
    if result.parsed is None:
        return result
    try:
        parsed = _parse_h6179_status(result.parsed)
    except AttributeError, IndexError, TypeError, ValueError:
        parsed = None
    if parsed is None:
        return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
    return ProtocolParseResult(parsed, result.parser, None)


def parse_h6179_status(frame: bytes) -> ParsedH6179Status | None:
    """Parse an H6179 reply into stable semantic fields."""
    return cast(ParsedH6179Status | None, parse_h6179_status_result(frame).parsed)


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

    model = protocol_model(model) or model
    if model == "H617A":
        root_type = {
            0x01: SceneType1Body,
            0x02: SceneBody,
            0x03: DiyType03,
            0x04: DiyType04,
        }.get(envelope[2])
        if root_type is None:
            raise ValueError(f"H617A A3 body type 0x{envelope[2]:02x} is not supported")
    elif model == "H6199":
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
    codec = _codec_for(model, "command")
    if codec.command_write is CommandWrite:
        return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd
    if codec.command_write is H6179CommandWrite:
        return (
            H6179CommandWrite,
            H6179CommandWrite.PowerBody,
            H6179CommandWrite.BrightnessBody,
        )
    if codec.command_write is H6199CommandWrite:
        return (
            H6199CommandWrite,
            H6199CommandWrite.PowerBody,
            H6199CommandWrite.BrightnessBody,
        )
    raise ValueError(f"{model} has no power/brightness command codec")


def new_child(struct_type: Any, parent: Any) -> Any:
    """Construct a read-write child struct bound to ``parent`` and its root."""
    return struct_type(None, parent, parent._root)


_child = new_child


def _build_status_query(
    domain: str,
    model: str = "H617A",
    *,
    display_setting: str | None = None,
    segment_group: int | None = None,
) -> bytes:
    codec = _codec_for(model, f"{domain} status-query")
    try:
        generated_domain = codec.query_domains[domain]
    except KeyError:
        raise ValueError(f"{model} has no {domain} status-query operation") from None
    root_type = codec.status_query
    root = root_type()
    root.header = b"\xaa"
    root.domain = (
        getattr(root_type.StatusDomain, cast(str, generated_domain))
        if root_type is H6179StatusQuery
        else getattr(root_type.QueryDomain, cast(str, generated_domain))
    )
    if display_setting is not None:
        if root_type is not H6199StatusQuery:
            raise ValueError(f"{model} has no display-setting status-query operation")
        body = _child(root_type.DisplaySettingQueryBody, root)
        body.setting = getattr(root_type.DisplaySetting, display_setting)
        body.zeros = [0] * 16
    elif segment_group is not None:
        if root_type not in {StatusQuery, H6199StatusQuery}:
            raise ValueError(f"{model} has no segment status-query operation")
        body = _child(root_type.SegmentQueryBody, root)
        body.group = segment_group
        body.zeros = [0] * 16
    elif root_type is H6179StatusQuery and domain in {"mode", "colour_mode"}:
        body = _child(root_type.ModeQueryBody, root)
        body.selector = root_type.ModeQuerySelector.current
        body.opaque = bytes(16)
    elif domain == "hardware":
        body = _child(root_type.HardwareQueryBody, root)
        body.selector = root_type.HardwareQuerySelector.primary if root_type is H6179StatusQuery else b"\x03"
        if root_type is H6179StatusQuery:
            body.opaque = bytes(16)
        else:
            body.zeros = [0] * 16
    elif domain == "relative_brightness":
        body = _child(root_type.RelativeBrightnessQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    else:
        if root_type is H6179StatusQuery:
            body = _child(root_type.OpaqueBody, root)
            body.opaque = bytes(17)
        else:
            body = _child(root_type.ZeroBody, root)
            body.zeros = [0] * 17
    root.body = body
    return _serialize_xor(root)


def build_power_query(model: str = "H617A") -> bytes:
    return _build_status_query("power", model)


def build_brightness_query(model: str = "H617A") -> bytes:
    return _build_status_query("brightness", model)


def build_colour_mode_query(model: str = "H617A") -> bytes:
    return _build_status_query("colour_mode", model)


def build_mode_query(model: str = "H6179") -> bytes:
    return _build_status_query("mode", model)


def build_firmware_query(model: str = "H617A") -> bytes:
    return _build_status_query("firmware", model)


def build_hardware_query(model: str = "H617A") -> bytes:
    return _build_status_query("hardware", model)


def build_h6199_white_balance_query() -> bytes:
    return _build_status_query("display_setting", "H6199", display_setting="white_balance")


def build_h6199_blank_screen_query() -> bytes:
    return _build_status_query("display_setting", "H6199", display_setting="blank_screen")


def build_h6199_relative_brightness_query() -> bytes:
    return _build_status_query("relative_brightness", "H6199")


def build_h6199_subordinate_query(domain: int) -> bytes:
    if domain not in {0x20, 0x21}:
        raise ValueError("H6199 subordinate query domain must be 0x20 or 0x21")
    return _build_status_query(f"subordinate_{domain:02x}", "H6199")


def build_segment_query(group: int, model: str = "H617A") -> bytes:
    resolved = wire_model(model)
    if resolved not in {"H617A", "H6199"}:
        raise ValueError(f"{model} has no segment status-query operation")
    maximum = 4 if resolved == "H6199" else 5
    if not 1 <= group <= maximum:
        raise ValueError(f"segment query group must be from 1 to {maximum}")
    return _build_status_query("segments", model, segment_group=group)


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
    content.family = H6199EffectUpload.EffectFamily(family)
    content.variant = variant
    content.speed = speed
    content.palette_len = len(palette) * 3
    content.palette = [new_rgb(content, colour) for colour in palette]
    root.content = content
    content.padding = [0] * h6199_diy_padding_len(len(palette))
    check_generated_tree(root)
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
    check_generated_tree(header)
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
    check_generated_tree(content)
    content_size = _serialized_length(content)
    if content_size + 3 > _A3_MAX_CONTENT:
        raise SceneParameterTooLargeError(
            f"Workshop content is {content_size + 3} bytes but the A3 line count only encodes {_A3_MAX_CONTENT}"
        )
    return _write(content, content_size)


def _set_effect_layer_lengths(records: list[Any]) -> None:
    for record in records:
        check_generated_tree(record.body)
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
    check_generated_tree(root)
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
    check_generated_tree(root)
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
    check_generated_tree(root)
    return _write(root, length)[3:]


def build_power(on: bool, model: str = "H617A") -> bytes:
    root_type, power_type, _ = _command_types(model)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOpcode.power if root_type is H6179CommandWrite else root_type.CommandOp.power
    body = power_type(None, root, root._root)
    body.is_on = int(on)
    if root_type is H6179CommandWrite:
        body.opaque = bytes(16)
    root.body = body
    return _serialize_xor(root)


def encode_h6179_brightness(percent: int) -> int:
    """Convert a semantic 1..100 brightness percentage to H6179 raw brightness."""
    if not isinstance(percent, int) or isinstance(percent, bool) or not 1 <= percent <= 100:
        raise ValueError("H6179 brightness must be an integer from 1 to 100")
    return (2000 + (percent - 1) * 237) // 100


def decode_h6179_brightness(raw: int) -> int:
    """Convert a candidate H6179 raw brightness byte to a percentage."""
    if not isinstance(raw, int) or isinstance(raw, bool) or not 20 <= raw <= 254:
        raise ValueError("H6179 raw brightness must be an integer from 20 to 254")
    scaled = (raw - 20) * 100
    return max(1, min(100, 1 - (-scaled // 237)))


def build_brightness(percent: int, model: str = "H617A") -> bytes:
    root_type, _, brightness_type = _command_types(model)
    root = root_type()
    root.header = b"\x33"
    root.opcode = (
        root_type.CommandOpcode.brightness if root_type is H6179CommandWrite else root_type.CommandOp.brightness
    )
    body = brightness_type(None, root, root._root)
    if root_type is H6179CommandWrite:
        body.raw = encode_h6179_brightness(percent)
        body.opaque = bytes(16)
    else:
        body.percent = max(0, min(100, percent))
    root.body = body
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


def _build_h6179_static_colour(
    *,
    direct: tuple[int, int, int],
    kelvin: int,
    preview: tuple[int, int, int],
) -> bytes:
    root = H6179CommandWrite()
    root.header = b"\x33"
    root.opcode = H6179CommandWrite.CommandOpcode.mode
    mode = _child(H6179CommandWrite.ModeBody, root)
    mode.mode = H6179CommandWrite.ModeSelector.static
    static = _child(H6179CommandWrite.StaticBody, mode)
    static.rgb_direct = _rgb(static, *direct)
    static.kelvin = kelvin
    static.rgb_preview = _rgb(static, *preview)
    static.opaque = bytes(8)
    mode.payload = static
    root.body = mode
    return _serialize_xor(root)


def build_segment_colour(
    mask: int,
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
) -> bytes:
    resolved = wire_model(model)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 static colour is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(red, green, blue),
            kelvin=0,
            preview=(0, 0, 0),
        )
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
    resolved = wire_model(model)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 colour temperature is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(255, 255, 255),
            kelvin=value,
            preview=preview,
        )
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
        direct=(0, 0, 0),
        kelvin=value,
        preview=preview,
    )


def build_segment_brightness(
    mask: int,
    percent: int,
    model: str = "H617A",
) -> bytes:
    value = max(0, min(100, percent))
    resolved = wire_model(model)
    if resolved == "H6179":
        raise ValueError("H6179 has no segment-brightness operation")
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


def build_h6179_scene(scene_code: int) -> bytes:
    if not isinstance(scene_code, int) or isinstance(scene_code, bool) or not 0 <= scene_code <= 0xFF:
        raise ValueError("H6179 scene code must be an integer from 0 to 255")
    root = H6179CommandWrite()
    root.header = b"\x33"
    root.opcode = H6179CommandWrite.CommandOpcode.mode
    mode = _child(H6179CommandWrite.ModeBody, root)
    mode.mode = H6179CommandWrite.ModeSelector.scene
    detail = _child(H6179CommandWrite.SceneBody, mode)
    detail.scene_id = scene_code
    detail.opaque = bytes(15)
    mode.payload = detail
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


def build_h6179_diy_activation(diy_code: int) -> bytes:
    if not isinstance(diy_code, int) or isinstance(diy_code, bool) or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("H6179 DIY code must be an integer from 0 to 65535")
    root = H6179CommandWrite()
    root.header = b"\x33"
    root.opcode = H6179CommandWrite.CommandOpcode.mode
    mode = _child(H6179CommandWrite.ModeBody, root)
    mode.mode = H6179CommandWrite.ModeSelector.diy
    detail = _child(H6179CommandWrite.DiyBody, mode)
    detail.diy_id = diy_code
    detail.opaque = bytes(14)
    mode.payload = detail
    root.body = mode
    return _serialize_xor(root)


def build_h6199_video(
    full_screen: bool,
    game_mode: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
) -> bytes:
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.mode
    mode = _child(H6199CommandWrite.ModeBody, root)
    mode.sub_mode = H6199CommandWrite.ModeSel.video
    detail = _child(H6199CommandWrite.VideoBody, mode)
    detail.region = H6199CommandWrite.VideoRegion.all if full_screen else H6199CommandWrite.VideoRegion.part
    detail.source = H6199CommandWrite.VideoSource.game if game_mode else H6199CommandWrite.VideoSource.movie
    detail.saturation = max(0, min(100, saturation))
    detail.sound_effects = int(sound_effects)
    detail.softness = max(1, min(100, softness))
    detail.relative_brightness_percent = 0
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def build_h6199_white_balance(red: int, blue: int) -> bytes:
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.display_setting
    body = _child(H6199CommandWrite.DisplaySettingBody, root)
    body.setting = H6199CommandWrite.DisplaySetting.white_balance
    body.len = 3
    payload = _child(H6199CommandWrite.WhiteBalancePayload, body)
    payload.manual = 1
    payload.red = max(0, min(255, red))
    payload.blue = max(0, min(255, blue))
    body.payload = payload
    root.body = body
    return _serialize_xor(root)


def build_h6199_blank_screen(
    enabled: bool,
    detection: int = 2,
    low_brightness_duration_seconds: int = _BLANK_SCREEN_LOW_BRIGHTNESS_SECONDS,
    same_tone_duration_seconds: int = _BLANK_SCREEN_SAME_TONE_SECONDS,
) -> bytes:
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


def build_h6199_relative_brightness(
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> bytes:
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.relative_brightness
    body = _child(H6199CommandWrite.RelativeBrightnessBody, root)
    body.selector = b"\x01"
    body.edge_count = 4
    body.left_percent = max(0, min(100, left))
    body.top_percent = max(0, min(100, top))
    body.right_percent = max(0, min(100, right))
    body.bottom_percent = max(0, min(100, bottom))
    body.strip_left_percent = 0
    body.strip_right_percent = 0
    root.body = body
    return _serialize_xor(root)


def build_music_mode(
    mode_id: int,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    model: str = "H617A",
) -> bytes:
    resolved = wire_model(model)
    if resolved == "H6179":
        profile = get_profile("H6179")
        if music_slug_for("H6179", mode_id) is None:
            raise ValueError(f"H6179 does not support music mode code 0x{mode_id:02x}")
        if (
            not isinstance(sensitivity, int)
            or isinstance(sensitivity, bool)
            or not profile.music_sensitivity_min <= sensitivity <= profile.music_sensitivity_max
        ):
            raise ValueError(
                "H6179 music sensitivity must be an integer from "
                f"{profile.music_sensitivity_min} to {profile.music_sensitivity_max}"
            )
        root = H6179CommandWrite()
        root.header = b"\x33"
        root.opcode = H6179CommandWrite.CommandOpcode.mode
        mode = _child(H6179CommandWrite.ModeBody, root)
        mode.mode = H6179CommandWrite.ModeSelector.music
        detail = _child(H6179CommandWrite.MusicBody, mode)
        detail.effect_id = mode_id
        detail.sensitivity = sensitivity
        detail.colour_mode = int(colour is not None)
        if colour is not None:
            detail.fixed_colour = _rgb(detail, *colour)
        detail.opaque = bytes(10 if colour is not None else 13)
        mode.payload = detail
        root.body = mode
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
