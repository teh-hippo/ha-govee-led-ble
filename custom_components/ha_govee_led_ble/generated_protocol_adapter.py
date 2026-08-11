"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
import math
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
StatusQuery = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.status_query").StatusQuery,
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
DiyType04 = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.diy_type04").DiyType04,
)
SceneBody = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.scene_body").SceneBody,
)

_A3_CHUNK_SIZE = 17

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
    except KaitaiStructError, UnicodeDecodeError:
        return None
    return parsed


def parse_command(frame: bytes, model: str = "H617A") -> Any | None:
    if len(frame) != 20 or xor_checksum(frame[:-1]) != frame[-1]:
        return None
    root_type = H6199CommandWrite if model == "H6199" else CommandWrite
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(frame)))
        parsed._read()
    except KaitaiStructError, UnicodeDecodeError:
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


def _build_status_query(
    domain: str,
    model: str = "H617A",
    *,
    display_setting: str | None = None,
) -> bytes:
    root_type = H6199StatusQuery if model == "H6199" else StatusQuery
    root = root_type()
    root.header = b"\xaa"
    root.domain = getattr(root_type.QueryDomain, domain)
    if display_setting is not None:
        body = _child(root_type.DisplaySettingQueryBody, root)
        body.setting = getattr(root_type.DisplaySetting, display_setting)
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
    return _build_status_query("power", model)


def build_brightness_query(model: str = "H617A") -> bytes:
    return _build_status_query("brightness", model)


def build_colour_mode_query(model: str = "H617A") -> bytes:
    return _build_status_query("colour_mode", model)


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


def _rgb(parent: Any, red: int, green: int, blue: int) -> Any:
    colour = _child(GoveeShared.Rgb, parent)
    colour.red = max(0, min(255, red))
    colour.green = max(0, min(255, green))
    colour.blue = max(0, min(255, blue))
    return colour


def _a3_header(parent: Any) -> Any:
    header = _child(GoveeCommon.A3Header, parent)
    header.marker = b"\x01"
    header.linecount = 2
    return header


def parse_scene_body_param(raw_param: bytes) -> Any:
    """Parse a catalogue type-2 parameter through the generated SceneBody root."""
    if not isinstance(raw_param, bytes):
        raise TypeError("scene parameter must be bytes")
    synthetic = SceneBody()
    header = _a3_header(synthetic)
    header_length = len(header.marker) + 1
    header.linecount = max(header.linecount, math.ceil((header_length + 1 + len(raw_param)) / _A3_CHUNK_SIZE))
    _check_tree(header)
    header_bytes = _write(header, header_length)
    envelope = header_bytes + bytes((int(SceneBody.SceneType.scene_v2),)) + raw_param
    unpadded = SceneBody(KaitaiStream(io.BytesIO(envelope)))
    unpadded._read()
    envelope = envelope.ljust(header.linecount * _A3_CHUNK_SIZE, b"\x00")
    parsed = SceneBody(KaitaiStream(io.BytesIO(envelope)))
    parsed._read()
    return parsed


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
