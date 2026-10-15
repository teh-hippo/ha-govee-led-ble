"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib import import_module
from types import MappingProxyType
from typing import Any, cast

from kaitaistruct import ConsistencyError, KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

from .const import ModelProfile, ReadDomain, get_profile
from .music_protocol import music_slug_for
from .music_semantics import MusicVariant, music_variant
from .transport import A3_CHUNK_SIZE, reassemble_a3, xor_checksum

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
H6199StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_status_reply").H6199StatusReply,
)
H6179StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6179_status_reply").H6179StatusReply,
)
H6102StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6102_status_reply").H6102StatusReply,
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
H6125StatusReply = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6125_status_reply").H6125StatusReply,
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
    "H6102": ("h6102_status_reply", H6102StatusReply),
    "H6125": ("h6125_status_reply", H6125StatusReply),
    "H6099": ("h6099_status_reply", H6099StatusReply),
    "H617A": ("status_reply", StatusReply),
    "H6179": ("h6179_status_reply", H6179StatusReply),
    "H6199": ("h6199_status_reply", H6199StatusReply),
}
_COMMAND_ROOTS = {
    "H601C": ("h601c_command_write", H601cCommandWrite),
    "H6099": ("h6099_command_write", H6099CommandWrite),
    "H617A": ("command_write", CommandWrite),
    "H6179": ("h6179_command_write", H6179CommandWrite),
    "H6199": ("h6199_command_write", H6199CommandWrite),
}
_STATUS_QUERY_ROOTS = {
    "H601C": ("status_query", StatusQuery),
    "H6099": ("h6099_status_query", H6099StatusQuery),
    "H617A": ("status_query", StatusQuery),
    "H6179": ("h6179_status_query", H6179StatusQuery),
    "H6199": ("h6199_status_query", H6199StatusQuery),
}
_COMMAND_ACK_ROOTS = {
    "H6099": ("h6099_command_ack", H6099CommandAck),
    "H617A": ("h617a_command_ack", H617aCommandAck),
    "H6199": ("h6199_command_ack", H6199CommandAck),
}


def _has_unknown_discriminator(parsed: Any, parser: str) -> bool:
    if getattr(parsed.opcode, "name", None) is None:
        return True
    if parser == "command_write" and parsed.opcode.name == "multi":
        return getattr(parsed.body.sub, "name", None) is None
    if parser == "h6199_command_write" and parsed.opcode.name == "mode":
        return getattr(parsed.body.sub_mode, "name", None) is None
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
    except KaitaiStructError, UnicodeDecodeError:
        return ProtocolParseResult(None, parser, ProtocolParseRejection.SCHEMA_REJECTED)
    return ProtocolParseResult(parsed, parser, None)


def parse_status_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    return _parse_xor_frame(frame, (profile or get_profile(model)).status_grammar, _STATUS_ROOTS)


def parse_status(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_status_result(frame, model, profile=profile).parsed


def parse_command_result(
    frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None
) -> ProtocolParseResult:
    result = _parse_xor_frame(frame, (profile or get_profile(model)).command_grammar, _COMMAND_ROOTS)
    if result.parsed is not None and _has_unknown_discriminator(result.parsed, result.parser or ""):
        return ProtocolParseResult(None, result.parser, ProtocolParseRejection.SEMANTIC_REJECTED)
    return result


def parse_command_ack_result(frame: bytes, model: str, *, profile: ModelProfile | None = None) -> ProtocolParseResult:
    profile = profile or get_profile(model)
    # Video companions retain their independently selected ACK codec. SDK ACKs
    # also exist on devices with no video grammar (notably H617A A3 uploads).
    if profile.video_grammar is not None:
        video = _parse_xor_frame(frame, profile.video_grammar, _COMMAND_ACK_ROOTS)
        if video.parsed is not None:
            return video
    return _parse_xor_frame(frame, profile.command_grammar, _COMMAND_ACK_ROOTS)


def upload_ack_subtype(packets: Sequence[bytes], index: int, model: str, *, profile: ModelProfile | None = None) -> int:
    """Validate a complete A3 upload ending at index, returning its ACK command."""
    if (profile or get_profile(model)).command_grammar != "H617A":
        raise ValueError("Upload ACK semantics are not qualified for this command grammar")
    roots = {"H617A": ("command_write.upload_frame", CommandWrite.UploadFrame)}
    for start in range(index, -1, -1):
        frame = _parse_xor_frame(packets[start], "H617A", roots).parsed
        if frame is None or (start == index and not frame.is_final):
            break
        if frame.index == 0:
            reassemble_a3(packets[start : index + 1])
            return int(frame.body.subtype)
    raise ValueError("Upload ACK index must end a complete A3 upload")


def upload_ack_success(parsed: Any, subtype: int) -> bool | None:
    """Return a matching upload result, never treating an ordinary ACK as A3."""
    if isinstance(parsed, H617aCommandAck) and parsed.is_upload and parsed.opcode == subtype:
        return bool(parsed.is_success)
    return None


def parse_command(frame: bytes, model: str = "H617A", *, profile: ModelProfile | None = None) -> Any | None:
    return parse_command_result(frame, model, profile=profile).parsed


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
            or detail.colour_mode not in {0, 1}
        ):
            return None
        colour = None
        if detail.colour_mode:
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
    parsed = _parse_xor_frame(frame, "H6179", _STATUS_QUERY_ROOTS).parsed
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


def boolean_control_name(operation: str) -> str | None:
    """Map named shared register semantics, never byte offsets or SKU identity."""
    return {"multi_effect": "gradual", "limit": "limit"}.get(operation)


def boolean_control_is_authorized(control: str, profile: ModelProfile) -> bool:
    """Retain the shipped H617A raw gradual register alongside explicit controls."""
    return control in profile.boolean_controls or (
        control == "gradual" and profile.status_grammar == "H617A" and profile.command_operations is None
    )


def require_profile_packet(frame: bytes, profile: ModelProfile) -> None:
    """Revalidate operation capabilities and geometry at each physical attempt."""
    from .light_commands import parse_static_write

    if profile.legacy_h6199_static_rgb and frame[:2] == b"\x33\x05":
        if frame[:3] != b"\x33\x05\x0b":
            raise ValueError(f"{profile.name} does not support this static-colour format")
        static = parse_static_write(frame, profile=profile)
        if static is None or static.rgb is None or not profile.supports_rgb:
            raise ValueError(f"{profile.name} does not support this static-colour packet")
        return

    command = _parse_xor_frame(frame, profile.command_grammar, _COMMAND_ROOTS).parsed
    if command is not None:
        operation = getattr(command.opcode, "name", "")
        control = boolean_control_name(operation)
        if control is not None:
            if boolean_control_is_authorized(control, profile):
                return
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        if (
            profile.command_operations is None
            or operation in profile.command_operations
            or "static" in profile.command_operations
            and getattr(command, "is_static", False)
        ):
            static = parse_static_write(frame, profile=profile)
            if static is None and getattr(command, "is_static", False) and profile.command_grammar == "H617A":
                levels = getattr(command.body.sub_body.static_body, "segment_percent", None)
                if levels is not None:
                    if not profile.supports_segments or not profile.supports_segment_brightness:
                        raise ValueError(f"{profile.name} does not support segment brightness")
                    if len(levels) != profile.segment_count or ((1 << len(levels)) - 1) & ~profile.whole_device_mask:
                        raise ValueError("segment brightness outside profile geometry")
            if static is not None:
                if profile.command_grammar == "H601C":
                    detail = command.body.detail
                    companion = bytes((detail.companion_rgb.red, detail.companion_rgb.green, detail.companion_rgb.blue))
                    expected_companion = _H601C_KELVIN_RGB.get(static.kelvin or 0, bytes(3))
                    if companion != expected_companion:
                        raise ValueError("H601C authored companion RGB does not match Kelvin")
                if static.segment_mask is not None and not static.segment_mask:
                    raise ValueError("no segments selected")
                if static.segment_mask is not None and (
                    not static.whole_strip
                    or (static.brightness_pct is not None and not profile.supports_white_brightness)
                ):
                    if not profile.supports_segments:
                        raise ValueError(f"{profile.name} does not support per-segment control")
                    if static.segment_mask & ~((1 << min(15, profile.segment_count)) - 1) or (
                        static.segment_mask & ~profile.whole_device_mask
                    ):
                        raise ValueError("segment mask outside profile geometry")
                if static.rgb is not None and not profile.supports_rgb:
                    raise ValueError(f"{profile.name} does not support RGB colour")
                if static.kelvin is not None:
                    if not profile.supports_color_temperature:
                        raise ValueError(f"{profile.name} does not support colour temperature")
                    if not static.whole_strip and not profile.supports_segment_color_temperature:
                        raise ValueError(f"{profile.name} does not support segment colour temperature")
                    if not profile.min_color_temp_kelvin <= static.kelvin <= profile.max_color_temp_kelvin:
                        raise ValueError("static Kelvin outside profile range")
                if static.brightness_pct is not None and not (
                    profile.supports_segments
                    and profile.supports_segment_brightness
                    or static.whole_strip
                    and profile.supports_white_brightness
                ):
                    raise ValueError(f"{profile.name} does not support segment brightness")
            return
    query = _parse_xor_frame(
        frame,
        profile.command_grammar,
        _STATUS_QUERY_ROOTS,
    ).parsed
    if query is not None:
        domain = getattr(query.domain, "name", "")
        control = boolean_control_name(domain)
        if control is not None:
            if boolean_control_is_authorized(control, profile):
                return
            raise ValueError(f"{profile.name} does not support boolean control {control}")
        if profile.command_operations is None or domain in profile.read_domains:
            return
    if profile.command_operations is None:
        return
    raise ValueError(f"{profile.name} does not support this operation")


def parse_a3_effect_envelope(envelope: bytes, model: str, *, profile: ModelProfile | None = None) -> Any:
    """Parse one validated, padded A3 effect envelope through its generated root."""
    if not isinstance(envelope, bytes):
        raise TypeError("A3 effect envelope must be bytes")
    if len(envelope) < A3_CHUNK_SIZE or len(envelope) % A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope must contain complete 17-byte chunks")
    if envelope[0] != 0x01:
        raise ValueError("A3 effect envelope has an invalid marker")
    if envelope[1] != len(envelope) // A3_CHUNK_SIZE:
        raise ValueError("A3 effect envelope does not match its chunk count")

    grammar = (profile or get_profile(model)).effect_grammar
    if grammar == "H617A":
        root_type = {
            0x01: SceneType1Body,
            0x02: SceneBody,
            0x03: DiyType03,
            0x04: DiyType04,
        }.get(envelope[2])
        if root_type is None:
            raise ValueError(f"H617A A3 body type 0x{envelope[2]:02x} is not supported")
    elif grammar == "H6099":
        root_type = H6099EffectUpload
    elif grammar == "H6199":
        root_type = H6199EffectUpload
    else:
        raise ValueError(f"{model} has no generated A3 effect grammar")

    try:
        parsed = root_type(KaitaiStream(io.BytesIO(envelope)))
        parsed._read()
        if grammar == "H6099" and int(parsed.kind) in (3, 4):
            _ = parsed.diy
    except KaitaiStructError as error:
        raise ValueError(f"invalid {model} A3 effect envelope") from error
    if not parsed._io.is_eof():
        raise ValueError(f"{model} A3 effect grammar did not consume the envelope")
    return parsed


def _command_types(model: str, profile: ModelProfile | None = None) -> tuple[Any, Any, Any]:
    resolved = (profile or get_profile(model)).command_grammar
    if resolved in {"H601C", "H6099", "H6179", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        return root_type, root_type.PowerBody, root_type.BrightnessBody
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
    colour_mode_selector: int = 0,
) -> bytes:
    if grammar not in _STATUS_QUERY_ROOTS:
        raise ValueError(f"{grammar} has no generated status-query grammar")
    root_type = _STATUS_QUERY_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\xaa"
    generated_domain = "mode" if grammar == "H6179" and domain == "colour_mode" else domain
    root.domain = getattr(
        root_type.StatusDomain if grammar == "H6179" else root_type.QueryDomain,
        generated_domain,
    )
    if display_setting is not None:
        body = _child(root_type.DisplaySettingQueryBody, root)
        body.setting = getattr(root_type.DisplaySetting, display_setting)
        body.zeros = [0] * 16
    elif segment_group is not None:
        if grammar == "H6179":
            raise ValueError("H6179 has no segment status-query operation")
        body = _child(root_type.SegmentQueryBody, root)
        body.group = segment_group
        body.zeros = [0] * 16
    elif domain == "hardware":
        body = _child(root_type.HardwareQueryBody, root)
        if grammar == "H6179":
            body.selector = root_type.HardwareQuerySelector.primary
            body.opaque = bytes(16)
        else:
            body.selector = b"\x03"
            body.zeros = [0] * 16
    elif domain == "relative_brightness":
        body = _child(root_type.RelativeBrightnessQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar == "H6099":
        body = _child(root_type.ColourModeQueryBody, root)
        body.selector = b"\x01"
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar in {"H601C", "H617A"}:
        body = _child(root_type.ColourModeQueryBody, root)
        body.selector = colour_mode_selector
        body.zeros = [0] * 16
    elif domain == "colour_mode" and grammar == "H6179":
        body = _child(root_type.ModeQueryBody, root)
        body.selector = root_type.ModeQuerySelector.current
        body.opaque = bytes(16)
    else:
        if grammar == "H6179":
            body = _child(root_type.OpaqueBody, root)
            body.opaque = bytes(17)
        else:
            body = _child(root_type.ZeroBody, root)
            body.zeros = [0] * 17
    root.body = body
    return _serialize_xor(root)


def build_power_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("power", (profile or get_profile(model)).command_grammar)


def build_brightness_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("brightness", (profile or get_profile(model)).command_grammar)


def build_colour_mode_query(
    model: str = "H617A", *, profile: ModelProfile | None = None, selector: int | None = None
) -> bytes:
    """Select the profile's AA05 query form, with an explicit override."""
    profile = profile or get_profile(model)
    if selector is None:
        selector = profile.colour_mode_query_selector
    if type(selector) is not int or selector not in (0, 1):
        raise ValueError("colour-mode query selector must be 0 or 1")
    return _build_status_query("colour_mode", profile.command_grammar, colour_mode_selector=selector)


def build_firmware_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("firmware", (profile or get_profile(model)).command_grammar)


def build_hardware_query(model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    return _build_status_query("hardware", (profile or get_profile(model)).command_grammar)


def build_boolean_control(control: str, enabled: bool, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Build a qualified shared register write; revision gating belongs to the profile."""
    profile = profile or get_profile(model)
    if control not in profile.boolean_controls or profile.command_grammar != "H617A":
        raise ValueError(f"{model} does not support boolean control {control}")
    if type(enabled) is not bool:
        raise ValueError("boolean control requires a boolean")
    operation = {"gradual": "multi_effect", "limit": "limit"}.get(control)
    if operation is None:
        raise ValueError("unknown boolean control")
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = getattr(CommandWrite.CommandOp, operation)
    root.body = _child(CommandWrite.MultiEffectCmd, root)
    root.body.flag = int(enabled)
    root.body.padding = [0] * 16
    return _serialize_xor(root)


def build_boolean_control_query(control: str, model: str, *, profile: ModelProfile | None = None) -> bytes:
    """Read a declared boolean register independently of ordinary read domains."""
    profile = profile or get_profile(model)
    if control not in profile.boolean_controls or profile.command_grammar != "H617A":
        raise ValueError(f"{model} does not support boolean control {control}")
    domain = {"gradual": "multi_effect", "limit": "limit"}.get(control)
    if domain is None:
        raise ValueError("unknown boolean control")
    return _build_status_query(domain, profile.command_grammar)


def parse_boolean_control(generated: Any, model: str, *, profile: ModelProfile | None = None) -> dict[str, bool]:
    """Decode register replies only; mode flags and command ACKs are not confirmation."""
    profile = profile or get_profile(model)
    if profile.status_grammar not in {"H617A", "H6102"}:
        return {}
    domain = getattr(getattr(generated, "domain", None), "name", "")
    control = boolean_control_name(domain)
    if control is None or control not in profile.boolean_controls:
        return {}
    flag = generated.body.flag
    if flag not in (0, 1):
        raise ValueError("boolean register reply must be 0 or 1")
    return {control: bool(flag)}


def build_physical_ic_count_query(model: str) -> bytes:
    if get_profile(model).command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified physical IC query")
    return _build_status_query("physical_ic_count", "H6099")


INSTALLATION_DIRECTIONS = (2, 3, 4, 5)

H6199_NATIVE_CONTROLS = ("strip_direction", "camera_position", "gradient", "camera_status")


def build_h6199_control_query(control: str) -> bytes:
    """Encode a named register query; callers must check runtime applicability."""
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


def build_installation_direction(value: int, model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_installation_direction or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified installation-direction writer")
    if type(value) is not int or value not in INSTALLATION_DIRECTIONS:
        raise ValueError("Installation direction must be 2, 3, 4, or 5")
    root = H6099CommandWrite()
    root.header = b"\x33"
    root.opcode = H6099CommandWrite.CommandOp.installation_direction
    root.body = _child(H6099CommandWrite.InstallationDirectionBody, root)
    root.body.value = value
    return _serialize_xor(root)


def build_installation_direction_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.can_read(ReadDomain.INSTALLATION_DIRECTION) or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified installation-direction query")
    return _build_status_query("installation_direction", profile.command_grammar)


def build_camera_health_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.can_read(ReadDomain.CAMERA_HEALTH) or profile.command_grammar != "H6099":
        raise ValueError(f"{model} has no qualified camera-health query")
    return _build_status_query("camera_health", profile.command_grammar)


def parse_physical_ic_count(generated: Any) -> int | None:
    if getattr(generated.domain, "name", None) != "physical_ic_count":
        return None
    count = int(generated.body.count)
    return count if count > 0 else None


def _video_grammar(model: str) -> str:
    profile = get_profile(model)
    if not profile.supports_video_mode or profile.video_grammar is None:
        raise ValueError(f"{model} does not support video mode")
    return profile.video_grammar


def build_white_balance_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_white_balance_readback or not profile.can_read(ReadDomain.DISPLAY_SETTING):
        raise ValueError(f"{model} does not support white-balance readback")
    if (grammar := profile.command_grammar) in {"H6099", "H6199"} or (
        grammar == "H617A" and profile.video_white_balance_representation == "scalar"
    ):
        setting = "scalar_white_balance" if profile.video_white_balance_representation == "scalar" else "white_balance"
        return _build_status_query("display_setting", grammar, display_setting=setting)
    raise ValueError(f"{model} has no generated white-balance query grammar")


def build_blank_screen_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_blank_screen:
        raise ValueError(f"{model} does not support blank-screen detection")
    if (grammar := _video_grammar(model)) in {"H6099", "H6199"}:
        return _build_status_query("display_setting", grammar, display_setting="blank_screen")
    raise ValueError(f"{model} has no generated blank-screen query grammar")


def build_relative_brightness_query(model: str) -> bytes:
    profile = get_profile(model)
    if not profile.supports_relative_brightness:
        raise ValueError(f"{model} does not support relative brightness")
    if (grammar := _video_grammar(model)) in {"H6099", "H6199"}:
        return _build_status_query("relative_brightness", grammar)
    raise ValueError(f"{model} has no generated relative-brightness query grammar")


def build_h6199_subordinate_query(domain: int) -> bytes:
    return build_subordinate_query(domain, "H6199")


def build_subordinate_query(domain: int, model: str) -> bytes:
    if domain not in {0x20, 0x21}:
        raise ValueError("subordinate query domain must be 0x20 or 0x21")
    profile = get_profile(model)
    if not profile.can_read(ReadDomain(f"subordinate_{domain:02x}")):
        raise ValueError(f"{model} does not support this subordinate identity query")
    return _build_status_query(f"subordinate_{domain:02x}", profile.command_grammar)


def build_black_border_query(model: str) -> bytes:
    if not get_profile(model).supports_black_border:
        raise ValueError(f"{model} does not support black-border removal")
    return _build_status_query("display_setting", _video_grammar(model), display_setting="black_border")


def build_segment_query(group: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    resolved = (profile or get_profile(model)).command_grammar
    if resolved not in {"H617A", "H6099", "H6199"}:
        raise ValueError(f"{model} has no generated segment-query grammar")
    maximum = 5 if resolved == "H617A" else 4
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


def build_power(on: bool, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    root_type, power_type, _ = _command_types(model, profile)
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOpcode.power if root_type is H6179CommandWrite else root_type.CommandOp.power
    body = power_type(None, root, root._root)
    body.is_on = int(on)
    if root_type is H6179CommandWrite:
        body.opaque = bytes(16)
    elif root_type is H601cCommandWrite:
        body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def encode_wire_brightness(percent: int, wire_range: tuple[int, int]) -> int:
    """Map a 1..100 percentage onto a device register range with the app's linear rule."""
    if not isinstance(percent, int) or isinstance(percent, bool) or not 1 <= percent <= 100:
        raise ValueError("brightness must be an integer from 1 to 100")
    low, high = wire_range
    return (low * 100 + (percent - 1) * (high - low + 3)) // 100


def decode_wire_brightness(raw: int, wire_range: tuple[int, int] | None) -> int:
    """Invert encode_wire_brightness; a register outside the declared range is not a brightness."""
    if wire_range is None:
        raise ValueError("brightness register range is not declared")
    low, high = wire_range
    if not isinstance(raw, int) or isinstance(raw, bool) or not low <= raw <= high:
        raise ValueError(f"brightness register must be an integer from {low} to {high}")
    return max(1, min(100, 1 - (-((raw - low) * 100) // (high - low + 3))))


_H6179_BRIGHTNESS_RANGE = (20, 254)


def encode_h6179_brightness(percent: int) -> int:
    """Convert a semantic 1..100 brightness percentage to H6179 raw brightness."""
    return encode_wire_brightness(percent, _H6179_BRIGHTNESS_RANGE)


def decode_h6179_brightness(raw: int) -> int:
    """Convert a candidate H6179 raw brightness byte to a percentage."""
    return decode_wire_brightness(raw, _H6179_BRIGHTNESS_RANGE)


def build_brightness(percent: int, model: str = "H617A", *, profile: ModelProfile | None = None) -> bytes:
    root_type, _, brightness_type = _command_types(model, profile)
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
    if root_type is H601cCommandWrite:
        body.padding = bytes(16)
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


# Android 7.6.01 Constant.java:469-546, getTemColorByKelvin:1061-1074.
# Complete first-match lookup in H601C's supported 2700..6500 range; no interpolation.
_H601C_KELVIN_RGB = {
    2700 + index * 100: bytes.fromhex(rgb)
    for index, rgb in enumerate(
        (
            "ffae54 ffb25b ffb662 ffb969 ffbd6f ffc076 ffc37c ffc682 ffc987 ffcb8d "
            "ffce92 ffd097 ffd39c ffd5a1 ffd7a6 ffd9ab ffdbaf ffddb4 ffdfb8 ffe1bc "
            "ffe2c0 ffe4c4 ffe5c8 ffe7cc ffe8d0 ffead3 ffebd7 ffedda ffeede ffefe1 "
            "fff0e4 fff1e7 fff3ea fff4ed fff5f0 fff6f3 fff7f7 fff8f8 fff9fb"
        ).split()
    )
}


def _build_h601c_static_colour(mask: int, direct: tuple[int, int, int], kelvin: int, profile: ModelProfile) -> bytes:
    if mask != profile.whole_device_mask or not mask:
        raise ValueError("H601C supports whole-device colour only")
    if kelvin and not 2700 <= kelvin <= 6500:
        raise ValueError("H601C Kelvin outside 2700..6500")
    if kelvin and kelvin not in _H601C_KELVIN_RGB:
        raise ValueError("H601C Kelvin must use 100 K steps from 2700 to 6500")
    root = H601cCommandWrite()
    root.header = b"\x33"
    root.opcode = H601cCommandWrite.CommandOp.mode
    mode = _child(H601cCommandWrite.ModeBody, root)
    mode.sub_mode = H601cCommandWrite.ModeSel.static_colour
    detail = _child(H601cCommandWrite.StaticColourBody, mode)
    detail.rgb = _rgb(detail, *direct)
    detail.kelvin = kelvin
    detail.companion_rgb = _rgb(detail, *_H601C_KELVIN_RGB.get(kelvin, bytes(3)))
    detail.padding = bytes(8)
    mode.detail = detail
    root.body = mode
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
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    resolved = profile.command_grammar
    if profile.legacy_h6199_static_rgb:
        if mask != profile.whole_device_mask:
            raise ValueError("H6199 Pact 1 capture qualifies whole-strip RGB only")
        frame = bytearray(20)
        frame[:3] = b"\x33\x05\x0b"
        frame[3:6] = bytes(max(0, min(255, value)) for value in (red, green, blue))
        frame[8:10] = profile.whole_device_mask.to_bytes(2, "little")
        frame[-1] = xor_checksum(frame[:-1])
        return bytes(frame)
    if resolved == "H601C":
        return _build_h601c_static_colour(mask, (red, green, blue), 0, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 static colour is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(red, green, blue),
            kelvin=0,
            preview=(0, 0, 0),
        )
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.colour
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
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    value = max(2000, min(9000, kelvin))
    profile = profile or get_profile(model)
    resolved = profile.command_grammar
    if resolved == "H601C":
        return _build_h601c_static_colour(mask, (255, 255, 255), kelvin, profile)
    if resolved == "H6179":
        if mask != 0:
            raise ValueError("H6179 colour temperature is inherently whole-device and has no segment mask")
        return _build_h6179_static_colour(
            direct=(255, 255, 255),
            kelvin=value,
            preview=preview,
        )
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.colour
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
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    value = max(0, min(100, percent))
    resolved = (profile or get_profile(model)).command_grammar
    if resolved == "H6179":
        raise ValueError("H6179 has no segment-brightness operation")
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.static_colour
        detail = _child(root_type.StaticColourBody, mode)
        detail.operation = root_type.StaticOperation.brightness
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
    profile: ModelProfile | None = None,
) -> bytes:
    """Encode a scene selector using only the target's evidenced command grammar."""
    grammar = (profile or get_profile(model)).command_grammar
    if grammar == "H617A":
        return build_h617a_scene(scene_code, scene_type=scene_type)
    if grammar == "H6179":
        if music_code or scene_type:
            raise ValueError("H6179 scene selector has no music-code or scene-type field")
        return build_h6179_scene(scene_code)
    if grammar == "H6199":
        return build_h6199_scene(scene_code, music_code)
    if grammar == "H6099":
        if music_code or scene_type:
            raise ValueError("H6099 scene selector has no music-code or scene-type field")
        root = H6099CommandWrite()
        root.header = b"\x33"
        root.opcode = H6099CommandWrite.CommandOp.mode
        mode = _child(H6099CommandWrite.ModeBody, root)
        mode.sub_mode = H6099CommandWrite.ModeSel.scene
        detail = _child(H6099CommandWrite.SceneBody, mode)
        detail.scene_id = scene_code
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)
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


def build_h6099_diy_activation(diy_code: int = 254) -> bytes:
    """Select a device-resident DIY code; this does not authorize DIY upload."""
    if type(diy_code) is not int or not 0 <= diy_code <= 0xFFFF:
        raise ValueError("DIY code must be an integer from 0 to 65535")
    root = H6099CommandWrite()
    root.header = b"\x33"
    root.opcode = H6099CommandWrite.CommandOp.mode
    mode = _child(H6099CommandWrite.ModeBody, root)
    mode.sub_mode = H6099CommandWrite.ModeSel.diy
    detail = _child(H6099CommandWrite.DiyBody, mode)
    detail.code = diy_code
    mode.detail = detail
    root.body = mode
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


def build_video_mode(
    video_mode: str,
    full_screen: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
    model: str,
    *,
    values: Mapping[str, Any] | None = None,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    if video_mode not in profile.video_modes:
        raise ValueError(f"{model} does not support video mode {video_mode}")
    profile.validate_video_saturation(saturation)
    grammar = profile.video_grammar
    parameters = validate_video_parameters(grammar, values or {})
    if grammar == "H66A0-video":
        if video_mode not in H66a0VideoCommand.VideoSource.__members__:
            raise ValueError("invalid video source")
        root = H66a0VideoCommand()
        root.header, root.opcode, root.mode = b"\x33", b"\x05", b"\x00"
        detail = _child(H66a0VideoCommand.VideoBody, root)
        detail.source = H66a0VideoCommand.VideoSource[video_mode]
        detail.picture_preset = H66a0VideoCommand.PicturePreset[parameters["picture_preset"]]
        detail.opaque = parameters["opaque"]
        detail.saturation = saturation
        if type(sound_effects) is not bool or type(softness) is not int or not 0 <= softness <= 100:
            raise ValueError("invalid video sound effects or softness")
        detail.sound_effects, detail.softness = int(sound_effects), softness
        root.detail = detail
        return _serialize_xor(root)
    if grammar not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated video-mode grammar")
    if video_mode not in {"movie", "game"}:
        raise ValueError(f"{model} video mode {video_mode} is not supported by the H6199 grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub_mode = root_type.ModeSel.video
    detail = _child(root_type.VideoBody, mode)
    detail.region = root_type.VideoRegion.all if full_screen else root_type.VideoRegion.part
    detail.source = root_type.VideoSource.game if video_mode == "game" else root_type.VideoSource.movie
    detail.saturation = saturation
    detail.sound_effects = int(sound_effects)
    detail.softness = max(1, min(100, softness))
    if grammar == "H6099":
        detail.sound_type = b"\x02"
    else:
        detail.relative_brightness_percent = 0
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def validate_video_parameters(grammar: str | None, values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate complete grammar-specific values; unknown bytes have no defaults."""
    if grammar == "H66A0-video":
        if set(values) != {"picture_preset", "opaque"}:
            raise ValueError("video requires picture_preset and opaque values; refresh the device first")
        if (
            not isinstance(values["picture_preset"], str)
            or values["picture_preset"] not in H66a0VideoCommand.PicturePreset.__members__
        ):
            raise ValueError("invalid video picture_preset")
        if type(values["opaque"]) is not int or not 0 <= values["opaque"] <= 255:
            raise ValueError("video opaque value must be a byte")
    elif values:
        raise ValueError("video grammar does not support these values")
    return dict(values)


def video_parameters_from_detail(detail: Any, grammar: str | None) -> dict[str, Any] | None:
    if grammar != "H66A0-video":
        return None
    return validate_video_parameters(
        grammar, {"picture_preset": getattr(detail.picture_preset, "name", None), "opaque": int(detail.opaque)}
    )


def parse_video_command(frame: bytes, model: str, *, profile: ModelProfile | None = None) -> Any | None:
    return _parse_xor_frame(
        frame,
        (profile or get_profile(model)).video_grammar,
        {"H66A0-video": ("h66a0_video_command", H66a0VideoCommand)},
    ).parsed


def build_h6199_video(
    full_screen: bool,
    game_mode: bool,
    saturation: int,
    sound_effects: bool,
    softness: int,
) -> bytes:
    return build_video_mode("game" if game_mode else "movie", full_screen, saturation, sound_effects, softness, "H6199")


def build_white_balance(red: int, blue: int | None, model: str, *, flag: int = 1) -> bytes:
    profile = get_profile(model)
    if not profile.supports_white_balance:
        raise ValueError(f"{model} does not support white balance")
    if (grammar := _video_grammar(model)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated white-balance grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    if profile.video_white_balance_representation == "scalar":
        if blue is not None or type(red) is not int or not 0 <= red <= 255:
            raise ValueError("scalar white balance requires one byte")
        body.setting = root_type.DisplaySetting.scalar_white_balance
        body.len = 1
        payload = _child(root_type.ScalarWhiteBalancePayload, body)
        payload.value = red
    else:
        if type(flag) is not int or flag not in (0, 1):
            raise ValueError("position white balance requires a known auto/manual flag")
        if any(type(value) is not int or not 0 <= value <= 255 for value in (red, blue)):
            raise ValueError("position white balance requires red and blue bytes")
        body.setting = root_type.DisplaySetting.white_balance
        body.len = 3
        payload = _child(root_type.WhiteBalancePayload, body)
        payload.manual = flag
        payload.red = red
        payload.blue = blue
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
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
    if type(enabled) is not bool or type(detection) is not int or detection not in (1, 2):
        raise ValueError("blank-screen policy requires a boolean and detection 1 or 2")
    if any(
        type(value) is not int or not 0 <= value <= 0xFFFF
        for value in (low_brightness_duration_seconds, same_tone_duration_seconds)
    ):
        raise ValueError("blank-screen durations must be integer seconds in 0..65535")
    if (grammar := _video_grammar(model)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated blank-screen grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    body.setting = root_type.DisplaySetting.blank_screen
    body.len = 6
    payload = _child(root_type.BlankScreenPayload, body)
    payload.is_on = int(enabled)
    payload.detection = root_type.BlankScreenDetection(detection)
    payload.low_brightness_duration_seconds = low_brightness_duration_seconds
    payload.same_tone_duration_seconds = same_tone_duration_seconds
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
    root.body = body
    return _serialize_xor(root)


def build_black_border(enabled: bool, model: str) -> bytes:
    if not get_profile(model).supports_black_border:
        raise ValueError(f"{model} does not support black-border removal")
    if type(enabled) is not bool:
        raise ValueError("black-border removal requires a boolean")
    grammar = _video_grammar(model)
    if grammar != "H6099":
        raise ValueError(f"{model} has no generated black-border grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.display_setting
    body = _child(root_type.DisplaySettingBody, root)
    body.setting = root_type.DisplaySetting.black_border
    body.len = 1
    payload = _child(root_type.BlackBorderPayload, body)
    payload.is_on = int(enabled)
    payload.unknown_tail = b""
    body.payload = payload
    body.unknown_tail = bytes(15 - body.len)
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
    if (grammar := _video_grammar(model)) not in {"H6099", "H6199"}:
        raise ValueError(f"{model} has no generated relative-brightness grammar")
    root_type = _COMMAND_ROOTS[grammar][1]
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.relative_brightness
    body = _child(root_type.RelativeBrightnessBody, root)
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
    *,
    profile: ModelProfile | None = None,
) -> bytes:
    profile = profile or get_profile(model)
    if type(mode_id) is not int or music_slug_for(model, mode_id) not in profile.music_modes:
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
        or (variant is not None and not variant.supports_fixed_colour)
        or len(colour) != 3
        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in colour)
    ):
        raise ValueError("fixed music colour is unsupported or invalid")
    resolved = profile.command_grammar
    if resolved == "H6179":
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
    if resolved in {"H6099", "H6199"}:
        root_type = _COMMAND_ROOTS[resolved][1]
        root = root_type()
        root.header = b"\x33"
        root.opcode = root_type.CommandOp.mode
        mode = _child(root_type.ModeBody, root)
        mode.sub_mode = root_type.ModeSel.music
        detail = _child(root_type.MusicBody, mode)
        detail.mode = root_type.MusicMode(mode_id)
        detail.sensitivity = max(0, min(100, sensitivity))
        if resolved == "H6199" or detail.is_legacy:
            detail.is_calm = int(calm)
            detail.has_fixed_colour = int(colour is not None)
            detail.fixed_colour = _rgb(detail, *(colour or (0, 0, 0)))
        elif colour is not None:
            raise ValueError("new H6099 music selectors omit fixed colour")
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
    if selector.is_legacy:
        selector.style = int(calm)
        selector.has_fixed_colour = int(colour is not None)
        if colour is not None:
            selector.rgb = _rgb(selector, *colour)
    elif colour is not None:
        raise ValueError("new H617A music selectors omit fixed colour")
    multi.sub_body = selector
    root.body = multi
    return _serialize_xor(root)


def _h6125_wire_music(selector: Any) -> bytes:
    root = H6125WireWrite()
    root.header = b"\x33"
    root.opcode = H6125WireWrite.CommandOp.mode
    mode = _child(H6125WireWrite.ModeBody, root)
    mode.sub = H6125WireWrite.ModeSub.music
    wire = _child(H6125WireWrite.MusicSelector, mode)
    name = getattr(selector.mode_id, "name", None)
    if name not in H6125WireWrite.MusicMode.__members__:
        raise ValueError(f"H6125 has no music selector for mode {selector.mode_id}")
    wire.mode_id = H6125WireWrite.MusicMode[name]
    wire.sensitivity = selector.sensitivity
    if name in {"rhythm", "spectrum", "rolling"}:
        colour = selector.rgb if selector.has_fixed_colour else None
        settings = _child(H6125WireWrite.RhythmSettings if name == "rhythm" else H6125WireWrite.ColourSettings, wire)
        if name == "rhythm":
            settings.style = selector.style
        settings.has_fixed_colour = int(colour is not None)
        if colour is not None:
            settings.rgb = _rgb(settings, colour.red, colour.green, colour.blue)
        settings.padding = bytes(14 - (2 if name == "rhythm" else 1) - (3 if colour is not None else 0))
    else:
        settings = _child(H6125WireWrite.OpaqueSettings, wire)
        settings.padding = bytes(14)
    wire.settings = settings
    mode.sub_body = wire
    root.body = mode
    return _serialize_xor(root)


def _h6125_wire_brightness(percent: int, wire_range: tuple[int, int]) -> bytes:
    root = H6125WireWrite()
    root.header = b"\x33"
    root.opcode = H6125WireWrite.CommandOp.brightness
    body = _child(H6125WireWrite.BrightnessBody, root)
    body.register = encode_wire_brightness(percent, wire_range)
    body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


@cache
def h6125_outbound_transform(wire_range: tuple[int, int]) -> Callable[[bytes], bytes]:
    """Re-encode the two H6125 writes whose layout differs from the shared logical frames."""

    def transform(packet: bytes) -> bytes:
        parsed = parse_command_result(packet, "H617A").parsed
        if parsed is None:
            return packet
        if parsed.opcode.name == "brightness":
            return _h6125_wire_brightness(int(parsed.body.percent), wire_range)
        if parsed.opcode.name == "multi" and parsed.body.sub.name == "music":
            return _h6125_wire_music(parsed.body.sub_body)
        return packet

    return transform


def music_default_palette(variant: MusicVariant | None) -> tuple[tuple[int, int, int], ...]:
    """Read the qualified default through its schema, not palette byte offsets."""
    if variant is None or not variant.template:
        raise ValueError("music palette layout is unqualified")
    root = parse_music_parameters(variant, variant.template)
    return tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in root.palette)


def parse_music_parameters(variant: MusicVariant, body: bytes) -> Any:
    """Validate a complete retained body with the selected KSY, independent of authoring bounds."""
    if not isinstance(body, bytes) or not body or len(body) > 255 * 17 - 3:
        raise ValueError("invalid music body length")
    if variant.layout == "h6099_music_parameters":
        root_type = import_module(
            "custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters"
        ).H6099MusicParameters
        root = root_type.from_bytes(body)
    elif variant.layout == "music_body":
        root = MusicBody.from_bytes(b"\x01\x02\x41" + body)
    else:
        raise ValueError("music palette layout is unqualified")
    root._read()
    if int(root.mode) != variant.mode_code or root.tail is None or not root._io.is_eof():
        raise ValueError("music body does not match qualified layout")
    return root


def encode_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    *,
    palette: list[tuple[int, int, int]] | None,
    calm: bool | None,
    physical_ic_count: int | None = None,
    preserve_companions: bool = False,
) -> bytes:
    """Edit named Kaitai fields; palette length never becomes an absolute tail offset."""
    if variant.layout == "h6099_music_parameters":
        return _encode_h6099_music_parameters(
            variant, parameters, palette, calm, physical_ic_count, preserve_companions
        )
    if variant.layout != "music_body" or not variant.evidence or not variant.template:
        raise ValueError("music parameter layout is unqualified")
    root = parse_music_parameters(variant, variant.template)
    length = len(variant.template) + 3
    if palette is not None:
        if variant.palette_bounds is None or not variant.palette_bounds[0] <= len(palette) <= variant.palette_bounds[1]:
            raise ValueError("palette count is outside music variant bounds")
        if any(
            len(rgb) != 3 or any(type(channel) is not int or not 0 <= channel <= 255 for channel in rgb)
            for rgb in palette
        ):
            raise ValueError("invalid music palette")
        length += 3 * (len(palette) - root.num_palette)
        root.num_palette = len(palette)
        root.palette = [_rgb(root, *rgb) for rgb in palette]
    tail = root.tail
    for spec in variant.parameters:
        if spec.profile_key not in parameters:
            continue
        if spec.requires_physical_ic_count and physical_ic_count is None:
            raise ValueError("music parameter requires known physical IC count")
        value = parameters[spec.profile_key]
        if not hasattr(tail, spec.wire_field):
            raise ValueError("music parameter field is absent from qualified layout")
        if spec.wire_field == "background":
            rgb = int(value)
            tail.background = _rgb(tail, rgb >> 16, (rgb >> 8) & 255, rgb & 255)
        elif spec.kind != "select":
            setattr(tail, spec.wire_field, int(value))
    if variant.gradient_companions is not None and "gradient" in parameters:
        tail.speed = variant.gradient_companions[bool(parameters["gradient"])]
    if variant.piano_derived_half and "key_count" in parameters:
        if (
            physical_ic_count is not None
            and not preserve_companions
            and any(spec.profile_key == "key_count" and spec.requires_physical_ic_count for spec in variant.parameters)
        ):
            from math import ceil

            tail.speed = 10 if physical_ic_count < 30 else 35
            tail.off_minimum = ceil(physical_ic_count / 4) if physical_ic_count < 30 else 1
        tail.off_maximum = max(tail.off_minimum, tail.key_count // 2)
    if variant.direction_values and "direction" in parameters:
        tail.start_point, tail.piece_num = {name: (start, pieces) for name, start, pieces in variant.direction_values}[
            str(parameters["direction"])
        ]
        if physical_ic_count is not None and any(
            spec.profile_key == "direction" and spec.requires_physical_ic_count for spec in variant.parameters
        ):
            tail.piece_len = 1 if physical_ic_count < 30 else 2 if tail.start_point == 1 else 3
    if variant.style_companions is not None and calm is not None:
        value = variant.style_companions[calm]
        if isinstance(tail, H617aControlPayload.ShinyTail):
            tail.minimum_brightness, tail.maximum_brightness = value >> 8, value & 255
        else:
            tail.no_rhythm_speed, tail.rhythm_speed = 10, value
    _check_tree(root)
    return _write(root, length)[3:]


def _encode_h6099_music_parameters(
    variant: MusicVariant,
    parameters: dict[str, int | bool | str],
    palette: list[tuple[int, int, int]] | None,
    calm: bool | None,
    ic: int | None,
    preserve_companions: bool = False,
) -> bytes:
    from math import ceil

    root_type = import_module(
        "custom_components.ha_govee_led_ble.generated_protocol.h6099_music_parameters"
    ).H6099MusicParameters
    root = root_type.from_bytes(variant.template)
    root._read()
    if root.mode != variant.mode_code or not variant.evidence:
        raise ValueError("music template does not match qualified variant")
    length = len(variant.template)
    if palette is not None:
        if variant.palette_bounds is None or not variant.palette_bounds[0] <= len(palette) <= variant.palette_bounds[1]:
            raise ValueError("palette count is outside music variant bounds")
        if any(len(rgb) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in rgb) for rgb in palette):
            raise ValueError("invalid music palette")
        length += 3 * (len(palette) - root.num_palette)
        root.num_palette = len(palette)
        root.palette = [_rgb(root, *rgb) for rgb in palette]
    tail = root.tail
    for spec in variant.parameters:
        if spec.profile_key not in parameters:
            continue
        value = parameters[spec.profile_key]
        if spec.wire_field == "background":
            rgb = int(value)
            tail.background = _rgb(tail, rgb >> 16, (rgb >> 8) & 255, rgb & 255)
        elif spec.kind != "select":
            setattr(tail, spec.wire_field, int(value))
    if variant.requires_physical_ic_count and ic is None:
        raise ValueError("music parameters require known physical IC count")
    if root.mode == 0x30 and calm is not None:
        tail.no_rhythm_speed, tail.rhythm_speed = 10, 20 if calm else 80
    elif root.mode == 0x31 and calm is not None:
        tail.minimum_brightness, tail.maximum_brightness = (20, 70) if calm else (5, 100)
    elif ic is not None:
        if root.mode == 0x32 and (not preserve_companions or "gradient" in parameters):
            tail.companion = (99, 98)[bool(tail.gradient)] if ic >= 30 else (97, 94)[bool(tail.gradient)]
        elif root.mode == 0x33 and not preserve_companions:
            tail.piece_count_min = max(1, ceil(ic * 3 / 25))
            tail.piece_count_max = max(1, ceil(ic * 2 / 5))
        elif root.mode == 0x34 and (not preserve_companions or "key_count" in parameters):
            if not preserve_companions:
                tail.speed = 10 if ic < 30 else 35
                tail.off_minimum = ceil(ic / 4) if ic < 30 else 1
            tail.off_maximum = max(tail.off_minimum, tail.key_count // 2)
        elif root.mode == 0x35 and (not preserve_companions or "direction" in parameters):
            tail.start_point = {"clockwise": 0, "counterclockwise": 2, "two_way": 1}[str(parameters["direction"])]
            two_way = tail.start_point == 1
            tail.piece_length = 1 if ic < 30 else 2 if two_way else 3
            tail.piece_count = (
                (ic // 4 if two_way else ic // 3) if ic < 30 else ceil(ic / 10 if two_way else ic * 4 / 25)
            )
            if not preserve_companions:
                tail.speed = 80 if ic < 30 else 85
        elif root.mode == 0x37 and not preserve_companions:
            tail.piece_count = max(1, ic // 2) if ic < 30 else ceil(ic * 7 / 50)
            # MusicMode.d uses default subEffect[0] (piece) as speed and [1] (10/20) as fade.
            tail.speed = max(1, min(50, tail.piece_count))
            tail.gradient = 0
    if any(
        type(value) is int and not 0 <= value <= 255 for key, value in vars(tail).items() if not key.startswith("_")
    ):
        raise ValueError("physical IC geometry exceeds music wire bounds")
    _check_tree(root)
    return _write(root, length)
