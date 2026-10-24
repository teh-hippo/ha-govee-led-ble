"""H6179 command and status adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from .const import get_profile
from .protocol_core import (
    _STATUS_QUERY_ROOTS,
    H6179CommandWrite,
    ProtocolParseRejection,
    ProtocolParseResult,
    _child,
    _parse_xor_frame,
    _rgb,
    _serialize_xor,
    decode_wire_brightness,
    encode_wire_brightness,
)


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
        mode_field = detail.effect_id if command else detail.music_id
        music_mode = getattr(mode_field, "name", None)
        mode_id = int(mode_field)
        if (
            music_mode is None
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
            music_mode=music_mode,
            music_mode_id=mode_id,
            sensitivity=int(detail.sensitivity),
            colour=colour,
        )
    return None


def parse_h6179_command(frame: bytes) -> ParsedH6179Command | None:
    """Parse an H6179 command into semantic values without exposing generated classes."""

    from .generated_protocol_adapter import parse_command

    parsed = parse_command(frame, "H6179")
    if parsed is None:
        return None
    operation = getattr(parsed.opcode, "name", None)
    if operation == "power":
        if parsed.body.is_on not in {0, 1} or not _has_zero_opaque(parsed.body):
            return None
        values = _values(is_on=bool(parsed.body.is_on))
    elif operation == "brightness":
        if not 20 <= int(parsed.body.raw) <= 254 or not _has_zero_opaque(parsed.body):
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

    from .generated_protocol_adapter import parse_status_result

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


_H6179_BRIGHTNESS_RANGE = (20, 254)


def encode_h6179_brightness(percent: int) -> int:
    """Convert a semantic 1..100 brightness percentage to H6179 raw brightness."""
    return encode_wire_brightness(percent, _H6179_BRIGHTNESS_RANGE)


def decode_h6179_brightness(raw: int) -> int:
    """Convert a candidate H6179 raw brightness byte to a percentage."""
    return decode_wire_brightness(raw, _H6179_BRIGHTNESS_RANGE)


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
