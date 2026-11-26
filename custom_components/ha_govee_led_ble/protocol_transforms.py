"""Per-model outbound wire transforms."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any

from .const import H6199_PACT1_PROFILE
from .protocol_core import (
    _STATUS_QUERY_ROOTS,
    H60a6LegacyWrite,
    H6046CommandWrite,
    H6053WireWrite,
    H6102WireWrite,
    H6117WireWrite,
    H6125LegacySegmentQuery,
    H6125WireWrite,
    H6127WireWrite,
    H6159WireWrite,
    H6181CommandWrite,
    H6199Pact1WireWrite,
    _child,
    _parse_xor_frame,
    _rgb,
    _serialize_xor,
    encode_wire_brightness,
)


@cache
def whole_rgb_outbound_transform(
    wire_range: tuple[int, int] | None, *, legacy_colour: bool, music_version: int | None
) -> Callable[[bytes], bytes]:
    """Translate the compatible logical whole-strip contract to its revision's wire shape."""

    def transform(packet: bytes) -> bytes:
        parsed = _parse_xor_frame(packet, "H6181", {"H6181": ("h6181_command_write", H6181CommandWrite)}).parsed
        if parsed is None:
            return packet
        operation = getattr(parsed.opcode, "name", None)
        if operation == "brightness" and wire_range is not None:
            return _register_brightness(H6159WireWrite, int(parsed.body.percent), wire_range)
        if operation != "mode":
            return packet
        mode = getattr(parsed.body.sub_mode, "name", None)
        detail = parsed.body.detail
        if mode == "static_colour" and legacy_colour:
            return _whole_rgb_colour_effect(parsed)
        if mode != "music" or music_version is None:
            return packet
        root = H6159WireWrite()
        root.header, root.opcode = b"\x33", H6159WireWrite.CommandOp.mode
        body = _child(H6159WireWrite.ModeBody, root)
        body.sub_mode = H6159WireWrite.ModeSel.legacy_music if music_version == 0 else H6159WireWrite.ModeSel.music
        music = _child(H6159WireWrite.LegacyMusicBody if music_version == 0 else H6159WireWrite.MusicBody, body)
        if music_version != 0:
            music.mode = H6159WireWrite.MusicMode(int(detail.mode))
        music.sensitivity = detail.sensitivity
        if music_version == 0 or int(detail.mode) in (0, 1):
            music.has_fixed_colour = detail.has_fixed_colour
            if detail.has_fixed_colour:
                rgb = detail.fixed_colour
                music.fixed_colour = _rgb(music, rgb.red, rgb.green, rgb.blue)
        music.padding = bytes(music.write_tail_size)
        body.detail, root.body = music, body
        return _serialize_xor(root)

    return transform


def _whole_rgb_colour_effect(command: Any) -> bytes:
    static = command.body.detail
    detail = _child(H6181CommandWrite.ColourEffectBody, command.body)
    detail.rgb = _rgb(detail, static.rgb.red, static.rgb.green, static.rgb.blue)
    detail.temperature_flag = int(bool(static.kelvin))
    detail.companion_rgb = _rgb(detail, static.companion_rgb.red, static.companion_rgb.green, static.companion_rgb.blue)
    detail.unknown_tail = bytes(9)
    command.body.sub_mode = H6181CommandWrite.ModeSel.colour_effect
    command.body.detail = detail
    return _serialize_xor(command)


def h6181_outbound_transform(packet: bytes, *, colour_effect: bool = False) -> bytes:
    parsed = _parse_xor_frame(packet, "H6181", {"H6181": ("h6181_command_write", H6181CommandWrite)}).parsed
    if parsed is None:
        return packet
    if getattr(parsed.opcode, "name", None) == "brightness":
        parsed.body.percent = encode_wire_brightness(int(parsed.body.percent), (20, 254))
        return _serialize_xor(parsed)
    if colour_effect and parsed.is_static:
        return _whole_rgb_colour_effect(parsed)
    return packet


def h6199_pact1_outbound_transform(packet: bytes) -> bytes:
    """Re-encode authorised H6199 controls that differ on Pact 1."""

    from .dreamview import is_legacy_dreamview_packet
    from .generated_protocol_adapter import parse_command

    profile = H6199_PACT1_PROFILE
    if is_legacy_dreamview_packet(packet):
        return packet
    if packet[:1] in {b"\xa1", b"\xa3", b"\xa4"}:
        return packet
    parsed = parse_command(packet, profile=profile)
    if parsed is None:
        return packet
    operation = parsed.body.sub_mode.name if parsed.opcode.name == "mode" else parsed.opcode.name
    if operation in {"power", "scene", "diy"}:
        return packet

    root = H6199Pact1WireWrite()
    root.header = b"\x33"
    if operation == "brightness":
        root.opcode = H6199Pact1WireWrite.CommandOp.brightness
        body = _child(H6199Pact1WireWrite.BrightnessBody, root)
        wire_range = profile.brightness_wire_range
        if wire_range is None:
            raise ValueError("H6199 Pact 1 brightness register range is not declared")
        body.register = encode_wire_brightness(int(parsed.body.percent), wire_range)
        body.unknown_tail = bytes(16)
    elif operation == "static_colour":
        root.opcode = H6199Pact1WireWrite.CommandOp.mode
        body = _child(H6199Pact1WireWrite.ModeBody, root)
        body.sub_mode = H6199Pact1WireWrite.ModeSel.static_colour
        detail = _child(H6199Pact1WireWrite.StaticColourBody, body)
        colour = parsed.body.detail
        detail.kelvin = int(colour.kelvin)
        detail.rgb = (
            _rgb(detail, int(colour.preview.red), int(colour.preview.green), int(colour.preview.blue))
            if detail.kelvin
            else _rgb(detail, int(colour.red), int(colour.green), int(colour.blue))
        )
        detail.segment_mask = int(colour.segment_mask)
        detail.unknown_tail = bytes(9)
        body.detail = detail
    elif operation == "music":
        root.opcode = H6199Pact1WireWrite.CommandOp.mode
        body = _child(H6199Pact1WireWrite.ModeBody, root)
        body.sub_mode = H6199Pact1WireWrite.ModeSel.music
        detail = _child(H6199Pact1WireWrite.MusicBody, body)
        music = parsed.body.detail
        detail.mode = H6199Pact1WireWrite.MusicMode[music.mode.name]
        detail.sensitivity = music.sensitivity
        if detail.mode == H6199Pact1WireWrite.MusicMode.rhythm:
            detail.is_calm = music.is_calm
        if detail.mode != H6199Pact1WireWrite.MusicMode.energetic:
            detail.has_fixed_colour = music.has_fixed_colour
            detail.fixed_colour = _rgb(
                detail, music.fixed_colour.red, music.fixed_colour.green, music.fixed_colour.blue
            )
        detail.unknown_tail = bytes(detail.write_tail_size)
        body.detail = detail
    else:
        raise ValueError("Unsupported H6199 Pact 1 wire operation")
    root.body = body
    return _serialize_xor(root)


def _h6125_wire_music(
    selector: Any,
    *,
    legacy: bool = False,
    root_type: Any = H6125WireWrite,
    selector_types: Any = None,
    music_sub: Any = None,
    mode_type: Any = None,
) -> bytes:
    types = root_type if selector_types is None else selector_types
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub = (
        music_sub if music_sub is not None else root_type.ModeSub.legacy_music if legacy else root_type.ModeSub.music
    )
    wire = _child(types.LegacyMusicSelector if legacy else types.MusicSelector, mode)
    if mode_type is None:
        mode_type = types.LegacyMusicMode if legacy else types.MusicMode
    name = getattr(selector.mode_id, "name", None)
    if name not in mode_type.__members__:
        raise ValueError(f"{root_type.__name__} has no music selector for mode {selector.mode_id}")
    wire.mode_id = mode_type[name]
    wire.sensitivity = selector.sensitivity
    if name in {"rhythm", "spectrum", "rolling"}:
        colour = selector.rgb if selector.has_fixed_colour else None
        rhythm = name == "rhythm" and not legacy
        settings = _child(types.RhythmSettings if rhythm else types.ColourSettings, wire)
        if rhythm:
            settings.style = selector.style
        settings.has_fixed_colour = int(colour is not None)
        if colour is not None:
            settings.rgb = _rgb(settings, colour.red, colour.green, colour.blue)
        settings.padding = bytes(14 - (2 if rhythm else 1) - (3 if colour is not None else 0))
    else:
        settings = _child(types.OpaqueSettings, wire)
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


@cache
def h6053_outbound_transform(
    wire_range: tuple[int, int] | None, *, legacy_colour: bool, legacy_music: bool
) -> Callable[[bytes], bytes]:
    """Translate independently selected brightness and two-bar colour wire formats."""

    def transform(packet: bytes) -> bytes:
        command = _parse_xor_frame(packet, "H6046", {"H6046": ("h6046_command_write", H6046CommandWrite)}).parsed
        if command is None:
            return packet
        if command.opcode == H6046CommandWrite.CommandOp.brightness and wire_range is not None:
            return _register_brightness(H6053WireWrite, int(command.body.percent), wire_range)
        if (
            legacy_music
            and command.opcode == H6046CommandWrite.CommandOp.mode
            and command.body.sub_mode == H6046CommandWrite.ModeSel.music
        ):
            root = H6053WireWrite()
            root.header, root.opcode = b"\x33", H6053WireWrite.CommandOp.mode
            mode = _child(H6053WireWrite.ModeBody, root)
            mode.sub_mode = H6053WireWrite.ModeSel.legacy_music
            detail = _child(H6053WireWrite.LegacyMusic, mode)
            music = command.body.detail
            detail.mode = H6053WireWrite.MusicMode[music.mode.name]
            detail.sensitivity = music.sensitivity
            if detail.is_base:
                if detail.mode == H6053WireWrite.MusicMode.rhythm:
                    detail.is_calm = music.is_calm
                detail.has_fixed_colour = music.has_fixed_colour
                if music.has_fixed_colour:
                    detail.bar_mask = music.bar_mask
                    detail.fixed_colour = _rgb(
                        detail, music.fixed_colour.red, music.fixed_colour.green, music.fixed_colour.blue
                    )
            detail.unknown_tail = bytes(detail.write_tail_size)
            mode.detail, root.body = detail, mode
            return _serialize_xor(root)
        if (
            not legacy_colour
            or command.opcode != H6046CommandWrite.CommandOp.mode
            or command.body.sub_mode != H6046CommandWrite.ModeSel.static_colour
        ):
            return packet
        static = command.body.detail
        if static.operation != H6046CommandWrite.StaticOperation.colour or not 1 <= static.segment_mask <= 3:
            raise ValueError("Legacy bar colour requires one or both complete bar targets")
        flags = H6053WireWrite.BarFlag
        root = H6053WireWrite()
        root.header, root.opcode = b"\x33", H6053WireWrite.CommandOp.mode
        mode = _child(H6053WireWrite.ModeBody, root)
        mode.sub_mode = H6053WireWrite.ModeSel.legacy_colour
        detail = _child(H6053WireWrite.LegacyColour, mode)
        detail.bar_mask = (int(flags.left) if static.segment_mask & 1 else 0) | (
            int(flags.right) if static.segment_mask & 2 else 0
        )
        colour = static.preview if static.kelvin else static
        detail.rgb = _rgb(detail, int(colour.red), int(colour.green), int(colour.blue))
        detail.kelvin, detail.unknown_tail = int(static.kelvin), bytes(10)
        mode.detail, root.body = detail, mode
        return _serialize_xor(root)

    return transform


def _h6125_wire_colour(static: Any, *, root_type: Any = H6125WireWrite, body_type: Any = None) -> bytes:
    if static.static_sub != 1 or static.static_body.kelvin:
        raise ValueError("Legacy RGB does not support Kelvin or segment brightness")
    root = root_type()
    root.header = b"\x33"
    root.opcode = root_type.CommandOp.mode
    mode = _child(root_type.ModeBody, root)
    mode.sub = root_type.ModeSub.legacy_colour
    body = _child(root_type.LegacyColour if body_type is None else body_type, mode)
    rgb = static.static_body.rgb_direct
    body.rgb = _rgb(body, rgb.red, rgb.green, rgb.blue)
    body.segment_mask = static.static_body.mask.bits
    body.padding = bytes(11)
    mode.sub_body = body
    root.body = mode
    return _serialize_xor(root)


@cache
def h6117_outbound_transform(
    wire_range: tuple[int, int] | None,
    *,
    legacy_colour: bool = False,
    whole_device: bool = False,
    legacy_music: bool = False,
) -> Callable[[bytes], bytes]:
    """Keep independently qualified H6117 register, RGB and music conversions separate."""
    from .generated_protocol_adapter import parse_command_result

    def transform(packet: bytes) -> bytes:
        parsed = parse_command_result(packet, "H617A").parsed
        if parsed is None:
            return packet
        if parsed.opcode.name == "brightness" and wire_range is not None:
            return _register_brightness(H6117WireWrite, int(parsed.body.percent), wire_range)
        if parsed.opcode.name != "multi":
            return packet
        if parsed.body.sub.name == "music" and legacy_music:
            return _h6125_wire_music(
                parsed.body.sub_body,
                root_type=H6117WireWrite,
                selector_types=H6125WireWrite,
                music_sub=H6117WireWrite.ModeSub.legacy_music,
                mode_type=H6117WireWrite.LegacyMusicMode,
            )
        if parsed.body.sub.name != "static":
            return packet
        static = parsed.body.sub_body
        if static.static_sub != 1 or static.static_body.kelvin:
            return packet
        if legacy_colour:
            return _h6125_wire_colour(
                static,
                root_type=H6117WireWrite,
                body_type=H6125WireWrite.LegacyColour,
            )
        if whole_device:
            if static.static_body.mask.bits != 1:
                raise ValueError("H6117 whole-device RGB does not support partial masks")
            root = H6117WireWrite()
            root.header = b"\x33"
            root.opcode = H6117WireWrite.CommandOp.mode
            mode = _child(H6117WireWrite.ModeBody, root)
            mode.sub = H6117WireWrite.ModeSub.whole_device_colour
            body = _child(H6117WireWrite.WholeDeviceColour, mode)
            rgb = static.static_body.rgb_direct
            body.rgb = _rgb(body, rgb.red, rgb.green, rgb.blue)
            body.unknown_tail = bytes(13)
            mode.sub_body, root.body = body, mode
            return _serialize_xor(root)
        return packet

    return transform


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


def rgb_only_segment_query_transform(packet: bytes) -> bytes:
    query = _parse_xor_frame(packet, "H617A", _STATUS_QUERY_ROOTS).parsed
    if query is None or getattr(query.domain, "name", None) != "segments":
        return packet
    root = H6125LegacySegmentQuery()
    root.header = b"\xaa"
    root.domain = H6125LegacySegmentQuery.QueryDomain.segments
    root.group = query.body.group
    root.padding = bytes(16)
    return _serialize_xor(root)


@cache
def dreamcolor_outbound_transform(
    wire_range: tuple[int, int],
    *,
    legacy_colour: bool = False,
    legacy_music: bool = False,
    whole_device_colour: bool = False,
    direct_music_colour: bool = False,
    legacy_gradual: bool = False,
) -> Callable[[bytes], bytes]:
    """Re-encode the revision's differing fields through its generated wire roots."""

    from .generated_protocol_adapter import parse_command_result

    def transform(packet: bytes) -> bytes:
        if legacy_gradual:
            query = _parse_xor_frame(packet, "H617A", _STATUS_QUERY_ROOTS).parsed
            if query is not None and getattr(query.domain, "name", None) == "multi_effect":
                root = H6127WireWrite.Query()
                root.header = b"\xaa"
                root.domain = H6127WireWrite.Query.QueryDomain.gradual
                root.unknown_tail = bytes(17)
                return _serialize_xor(root)
        if legacy_colour:
            transformed = rgb_only_segment_query_transform(packet)
            if transformed != packet:
                return transformed
        parsed = parse_command_result(packet, "H617A").parsed
        if parsed is None:
            return packet
        if parsed.opcode.name == "brightness":
            return _register_brightness(H6125WireWrite, int(parsed.body.percent), wire_range)
        if legacy_gradual and parsed.opcode.name == "multi_effect":
            root = H6127WireWrite()
            root.header = b"\x33"
            root.opcode = H6127WireWrite.CommandOp.gradual
            body = _child(H6127WireWrite.FlagBody, root)
            body.flag = parsed.body.flag
            body.unknown_tail = bytes(16)
            root.body = body
            return _serialize_xor(root)
        if parsed.opcode.name == "multi" and parsed.body.sub.name == "music" and direct_music_colour:
            selector = parsed.body.sub_body
            root = H6127WireWrite()
            root.header = b"\x33"
            root.opcode = H6127WireWrite.CommandOp.mode
            mode = _child(H6127WireWrite.ModeBody, root)
            mode.sub = H6127WireWrite.ModeSub.legacy_music
            body = _child(H6127WireWrite.LegacyMusicSelector, mode)
            body.mode_id = H6127WireWrite.LegacyMusicMode[selector.mode_id.name]
            body.sensitivity = selector.sensitivity
            fixed = body.mode_id in {H6127WireWrite.LegacyMusicMode.spectrum, H6127WireWrite.LegacyMusicMode.rolling}
            if fixed:
                if not selector.has_fixed_colour:
                    raise ValueError("This legacy music selector requires a fixed colour")
                rgb = selector.rgb
                body.rgb = _rgb(body, rgb.red, rgb.green, rgb.blue)
            body.unknown_tail = bytes(11 if fixed else 14)
            mode.sub_body, root.body = body, mode
            return _serialize_xor(root)
        if parsed.opcode.name == "multi" and parsed.body.sub.name == "music":
            return _h6125_wire_music(parsed.body.sub_body, legacy=legacy_music)
        if legacy_colour and parsed.opcode.name == "multi" and parsed.body.sub.name == "static":
            return _h6125_wire_colour(parsed.body.sub_body)
        if whole_device_colour and parsed.opcode.name == "multi" and parsed.body.sub.name == "static":
            static = parsed.body.sub_body
            if static.static_sub != 1 or static.static_body.mask.bits != 1:
                raise ValueError("Whole-device colour does not support partial masks or segment brightness")
            colour = static.static_body
            root = H6127WireWrite()
            root.header = b"\x33"
            root.opcode = H6127WireWrite.CommandOp.mode
            mode = _child(H6127WireWrite.ModeBody, root)
            mode.sub = H6127WireWrite.ModeSub.whole_device_colour
            body = _child(H6127WireWrite.WholeDeviceColour, mode)
            body.rgb = _rgb(body, colour.rgb_direct.red, colour.rgb_direct.green, colour.rgb_direct.blue)
            body.temperature_flag = int(bool(colour.kelvin))
            body.companion_rgb = _rgb(body, colour.rgb_preview.red, colour.rgb_preview.green, colour.rgb_preview.blue)
            body.unknown_tail = bytes(9)
            mode.sub_body, root.body = body, mode
            return _serialize_xor(root)
        return packet

    return transform
