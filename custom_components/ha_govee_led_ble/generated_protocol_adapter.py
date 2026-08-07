"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
from importlib import import_module
from typing import Any, cast

from kaitaistruct import KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.command_write").CommandWrite,
)
H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
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

_BLANK_SCREEN_PARAMETERS = b"\x02\x0a\x00\x78\x00"


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


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for part in data:
        checksum ^= part
    return checksum


def _serialize_xor(root: Any, length: int = 20) -> bytes:
    root.checksum = 0
    _check_tree(root)
    provisional = _write(root, length)
    root.checksum = xor_checksum(provisional[:-1])
    _check_tree(root)
    return _write(root, length)


def parse_status(frame: bytes, model: str = "H617A") -> Any | None:
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    root_type = H6199StatusReply if model == "H6199" else StatusReply
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError:
        return None
    return parsed


def _command_types(model: str) -> tuple[Any, Any, Any]:
    if model == "H6199":
        return (
            H6199CommandWrite,
            H6199CommandWrite.PowerBody,
            H6199CommandWrite.BrightnessBody,
        )
    return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd


def _child(child_type: Any, parent: Any) -> Any:
    return child_type(None, parent, parent._root)


def _rgb(parent: Any, red: int, green: int, blue: int) -> Any:
    colour = _child(GoveeShared.Rgb, parent)
    colour.red = max(0, min(255, red))
    colour.green = max(0, min(255, green))
    colour.blue = max(0, min(255, blue))
    return colour


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


def build_segment_colour(
    mask: int,
    red: int,
    green: int,
    blue: int,
    model: str = "H617A",
) -> bytes:
    if model == "H6199":
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

    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.static
    static = _child(CommandWrite.StaticCmd, multi)
    static.static_sub = 1
    colour = _child(CommandWrite.StaticColor, static)
    colour.rgb_direct = _rgb(colour, red, green, blue)
    colour.kelvin = 0
    colour.rgb_preview = _rgb(colour, 0, 0, 0)
    segment_mask = _child(CommandWrite.SegmentMask, colour)
    segment_mask.bits = mask
    colour.mask = segment_mask
    static.static_body = colour
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_colour_temperature(
    kelvin: int,
    preview: tuple[int, int, int],
    model: str = "H617A",
) -> bytes:
    value = max(2000, min(9000, kelvin))
    if model == "H6199":
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
        detail.segment_mask = 0x7FFF
        mode.detail = detail
        root.body = mode
        return _serialize_xor(root)

    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.static
    static = _child(CommandWrite.StaticCmd, multi)
    static.static_sub = 1
    colour = _child(CommandWrite.StaticColor, static)
    colour.rgb_direct = _rgb(colour, 0, 0, 0)
    colour.kelvin = value
    colour.rgb_preview = _rgb(colour, *preview)
    segment_mask = _child(CommandWrite.SegmentMask, colour)
    segment_mask.bits = 0x7FFF
    colour.mask = segment_mask
    static.static_body = colour
    multi.sub_body = static
    root.body = multi
    return _serialize_xor(root)


def build_segment_brightness(
    mask: int,
    percent: int,
    model: str = "H617A",
) -> bytes:
    value = max(0, min(100, percent))
    if model == "H6199":
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
    mode.detail = detail
    root.body = mode
    return _serialize_xor(root)


def build_h617a_scene(scene_code: int) -> bytes:
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.scene
    detail = _child(CommandWrite.SceneActivate, multi)
    detail.code = max(0, min(0xFFFF, scene_code))
    detail.scene_type = 0
    multi.sub_body = detail
    root.body = multi
    return _serialize_xor(root)


def build_h617a_diy(slot: int, type_byte: int | None = None) -> bytes:
    root = CommandWrite()
    root.header = b"\x33"
    root.opcode = CommandWrite.CommandOp.multi
    multi = _child(CommandWrite.MultiCmd, root)
    multi.sub = CommandWrite.MultiSub.diy
    detail = _child(GoveeCommon.DiySelector, multi)
    detail.slot = max(0, min(255, slot))
    detail.type_byte = max(0, min(255, type_byte or 0))
    multi.sub_body = detail
    root.body = multi
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


def build_h6199_blank_screen(enabled: bool) -> bytes:
    root = H6199CommandWrite()
    root.header = b"\x33"
    root.opcode = H6199CommandWrite.CommandOp.display_setting
    body = _child(H6199CommandWrite.DisplaySettingBody, root)
    body.setting = H6199CommandWrite.DisplaySetting.blank_screen
    body.len = 6
    payload = _child(H6199CommandWrite.BlankScreenPayload, body)
    payload.is_on = int(enabled)
    payload._unnamed1 = _BLANK_SCREEN_PARAMETERS
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
    root.body = body
    return _serialize_xor(root)


def build_music_mode(
    mode_id: int,
    sensitivity: int,
    colour: tuple[int, int, int] | None,
    calm: bool,
    model: str = "H617A",
) -> bytes:
    if model == "H6199":
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
