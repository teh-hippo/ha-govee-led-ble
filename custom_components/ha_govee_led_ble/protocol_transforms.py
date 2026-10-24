"""Per-model outbound wire transforms."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any

from .const import H6199_PACT1_PROFILE
from .protocol_core import (
    _STATUS_QUERY_ROOTS,
    H60a6LegacyWrite,
    H6102WireWrite,
    H6125LegacySegmentQuery,
    H6125WireWrite,
    H6199Pact1WireWrite,
    _child,
    _parse_xor_frame,
    _rgb,
    _serialize_xor,
    encode_wire_brightness,
)


def h6199_pact1_outbound_transform(packet: bytes) -> bytes:
    """Re-encode authorised logical H6199 brightness and RGB through the legacy wire root."""

    from .generated_protocol_adapter import parse_command, require_profile_packet

    profile = H6199_PACT1_PROFILE
    require_profile_packet(packet, profile)
    parsed = parse_command(packet, profile=profile)
    if parsed is None or parsed.opcode.name == "power":
        return packet

    root = H6199Pact1WireWrite()
    root.header = b"\x33"
    if parsed.opcode.name == "brightness":
        root.opcode = H6199Pact1WireWrite.CommandOp.brightness
        body = _child(H6199Pact1WireWrite.BrightnessBody, root)
        wire_range = profile.brightness_wire_range
        if wire_range is None:
            raise ValueError("H6199 Pact 1 brightness register range is not declared")
        body.register = encode_wire_brightness(int(parsed.body.percent), wire_range)
        body.unknown_tail = bytes(16)
    else:
        root.opcode = H6199Pact1WireWrite.CommandOp.mode
        body = _child(H6199Pact1WireWrite.ModeBody, root)
        body.sub_mode = H6199Pact1WireWrite.ModeSel.static_colour
        detail = _child(H6199Pact1WireWrite.StaticColourBody, body)
        colour = parsed.body.detail
        detail.rgb = _rgb(detail, int(colour.red), int(colour.green), int(colour.blue))
        detail.kelvin = 0
        detail.segment_mask = int(colour.segment_mask)
        detail.unknown_tail = bytes(9)
        body.detail = detail
    root.body = body
    return _serialize_xor(root)


def _h6125_wire_music(selector: Any, *, legacy: bool = False, root_type: Any = H6125WireWrite) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub = root_type.ModeSub.legacy_music if legacy else root_type.ModeSub.music
    wire = _child(root_type.LegacyMusicSelector if legacy else root_type.MusicSelector, mode)
    mode_type = root_type.LegacyMusicMode if legacy else root_type.MusicMode
    name = getattr(selector.mode_id, "name", None)
    if name not in mode_type.__members__:
        raise ValueError(f"{root_type.__name__} has no music selector for mode {selector.mode_id}")
    wire.mode_id = mode_type[name]
    wire.sensitivity = selector.sensitivity
    if name in {"rhythm", "spectrum", "rolling"}:
        colour = selector.rgb if selector.has_fixed_colour else None
        rhythm = name == "rhythm" and not legacy
        settings = _child(root_type.RhythmSettings if rhythm else root_type.ColourSettings, wire)
        if rhythm:
            settings.style = selector.style
        settings.has_fixed_colour = int(colour is not None)
        if colour is not None:
            settings.rgb = _rgb(settings, colour.red, colour.green, colour.blue)
        settings.padding = bytes(14 - (2 if rhythm else 1) - (3 if colour is not None else 0))
    else:
        settings = _child(root_type.OpaqueSettings, wire)
        settings.padding = bytes(14)
    wire.settings = settings
    mode.sub_body = wire
    root.body = mode
    return _serialize_xor(root)


def _register_brightness(root_type: Any, percent: int, wire_range: tuple[int, int]) -> bytes:
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.brightness
    body = _child(root_type.BrightnessBody, root)
    body.register = encode_wire_brightness(percent, wire_range)
    body.padding = bytes(16)
    root.body = body
    return _serialize_xor(root)


def _h6125_wire_colour(static: Any, *, root_type: Any = H6125WireWrite) -> bytes:
    if static.static_sub != 1 or static.static_body.kelvin:
        raise ValueError("Legacy RGB does not support Kelvin or segment brightness")
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub = root_type.ModeSub.legacy_colour
    body = _child(root_type.LegacyColour, mode)
    rgb = static.static_body.rgb_direct
    body.rgb = _rgb(body, rgb.red, rgb.green, rgb.blue)
    body.segment_mask = static.static_body.mask.bits
    body.padding = bytes(11)
    mode.sub_body = body
    root.body = mode
    return _serialize_xor(root)


@cache
def h6102_outbound_transform_for(*, legacy_colour: bool = False) -> Callable[[bytes], bytes]:
    """Re-encode H6102 Pact 1 brightness, 0x11 music, and optional 0x0b segment RGB."""

    from .generated_protocol_adapter import parse_command_result

    def transform(packet: bytes) -> bytes:
        parsed = parse_command_result(packet, "H617A").parsed
        if parsed is None:
            return packet
        if parsed.opcode.name == "brightness":
            return _register_brightness(H6102WireWrite, int(parsed.body.percent), (20, 254))
        if parsed.opcode.name == "multi" and parsed.body.sub.name == "music":
            return _h6125_wire_music(parsed.body.sub_body, root_type=H6102WireWrite)
        if legacy_colour and parsed.opcode.name == "multi" and parsed.body.sub.name == "static":
            return _h6125_wire_colour(parsed.body.sub_body, root_type=H6102WireWrite)
        return packet

    return transform


def h60a6_legacy_outbound_transform(packet: bytes) -> bytes:
    """Re-encode the admitted whole-device static request through the Pact 1/1 root."""

    from .generated_protocol_adapter import parse_command_result

    parsed = parse_command_result(packet, "H617A").parsed
    if parsed is None or not parsed.is_static:
        return packet
    static = parsed.body.sub_body
    if static.static_sub != 1 or static.static_body.mask.bits != 1:
        raise ValueError("Legacy whole-device colour does not support selected segments")
    colour = static.static_body
    root = H60a6LegacyWrite()
    root.header = b"\x33\x05\x0d"
    root.rgb_direct = _rgb(root, colour.rgb_direct.red, colour.rgb_direct.green, colour.rgb_direct.blue)
    root.kelvin = colour.kelvin
    root.rgb_preview = _rgb(root, colour.rgb_preview.red, colour.rgb_preview.green, colour.rgb_preview.blue)
    root.unknown_tail = bytes(8)
    return _serialize_xor(root)


@cache
def h6125_outbound_transform(
    wire_range: tuple[int, int], *, legacy_colour: bool = False, legacy_music: bool = False
) -> Callable[[bytes], bytes]:
    """Re-encode the revision's differing fields through its generated wire roots."""

    from .generated_protocol_adapter import parse_command_result

    def transform(packet: bytes) -> bytes:
        if legacy_colour:
            query = _parse_xor_frame(packet, "H617A", _STATUS_QUERY_ROOTS).parsed
            if query is not None and getattr(query.domain, "name", None) == "segments":
                root = H6125LegacySegmentQuery()
                root.header = b"\xaa"
                root.domain = H6125LegacySegmentQuery.QueryDomain.segments
                root.group = query.body.group
                root.padding = bytes(16)
                return _serialize_xor(root)
        parsed = parse_command_result(packet, "H617A").parsed
        if parsed is None:
            return packet
        if parsed.opcode.name == "brightness":
            return _register_brightness(H6125WireWrite, int(parsed.body.percent), wire_range)
        if parsed.opcode.name == "multi" and parsed.body.sub.name == "music":
            return _h6125_wire_music(parsed.body.sub_body, legacy=legacy_music)
        if legacy_colour and parsed.opcode.name == "multi" and parsed.body.sub.name == "static":
            return _h6125_wire_colour(parsed.body.sub_body)
        return packet

    return transform
