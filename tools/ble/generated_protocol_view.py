"""Standalone model-aware views over the committed generated Kaitai classes."""

from __future__ import annotations

import io
import sys
from functools import cache
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from kaitaistruct import KaitaiStream, KaitaiStructError, ReadWriteKaitaiStruct

MODELS = ("H617A", "H6199")
FRAME_LENGTH = 20
_PACKAGE = "custom_components.ha_govee_led_ble.generated_protocol"


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for part in data:
        checksum ^= part
    return checksum


def sum8_checksum(data: bytes | bytearray) -> int:
    return sum(data) & 0xFF


def _generated_dir() -> Path:
    sibling = Path(__file__).resolve().parent / "generated_protocol"
    if sibling.is_dir():
        return sibling
    return Path(__file__).resolve().parents[2] / "custom_components/ha_govee_led_ble/generated_protocol"


def _namespace(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    module = ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def _prepare_generated_package() -> None:
    generated = _generated_dir()
    _namespace("custom_components", generated.parents[2])
    _namespace("custom_components.ha_govee_led_ble", generated.parent)
    _namespace(_PACKAGE, generated)


@cache
def _generated_class(module_name: str, class_name: str) -> Any:
    _prepare_generated_package()
    return getattr(import_module(f"{_PACKAGE}.{module_name}"), class_name)


def _read(module_name: str, class_name: str, data: bytes, *, checksum: str = "xor") -> Any | None:
    if checksum == "xor":
        if len(data) != FRAME_LENGTH or xor_checksum(data[:-1]) != data[-1]:
            return None
    elif checksum == "sum8":
        if len(data) != 7 or sum8_checksum(data[:-1]) != data[-1]:
            return None
    root_type = _generated_class(module_name, class_name)
    try:
        parsed = root_type(KaitaiStream(io.BytesIO(data)))
        parsed._read()
    except KaitaiStructError, UnicodeDecodeError:
        return None
    return parsed


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


def _serialize_xor(root: Any) -> bytes:
    root.checksum = 0
    _check_tree(root)
    provisional = _write(root, FRAME_LENGTH)
    root.checksum = xor_checksum(provisional[:-1])
    _check_tree(root)
    return _write(root, FRAME_LENGTH)


def _child(child_type: Any, parent: Any) -> Any:
    return child_type(None, parent, parent._root)


def _build_query(model: str, domain: str, *, display_setting: str | None = None) -> bytes:
    if model == "H6199":
        root_type = _generated_class("h6199_status_query", "H6199StatusQuery")
    elif model == "H617A":
        root_type = _generated_class("status_query", "StatusQuery")
    else:
        raise ValueError(f"unsupported model {model!r}")
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


def query_frames(model: str) -> tuple[tuple[str, bytes], ...]:
    queries = [
        ("power", _build_query(model, "power")),
        ("brightness", _build_query(model, "brightness")),
        ("colour_mode", _build_query(model, "colour_mode")),
        ("firmware", _build_query(model, "firmware")),
        ("hardware", _build_query(model, "hardware")),
    ]
    if model == "H6199":
        queries.extend(
            (
                ("white_balance", _build_query(model, "display_setting", display_setting="white_balance")),
                ("blank_screen", _build_query(model, "display_setting", display_setting="blank_screen")),
                ("relative_brightness", _build_query(model, "relative_brightness")),
            )
        )
    return tuple(queries)


def _enum_name(value: Any) -> str | None:
    return getattr(value, "name", None)


def _named(value: Any) -> str:
    return _enum_name(value) or f"{int(value):#04x}"


def _rgb(value: Any) -> str:
    return f"({int(value.red)},{int(value.green)},{int(value.blue)})"


def _segment_mask(bits: int) -> str:
    if bits == 0x7FFF:
        return "0x7fff(all)"
    segments = [str(index + 1) for index in range(15) if bits & (1 << index)]
    return f"0x{bits:04x}(seg {','.join(segments) if segments else '-'})"


def _format_h617a_command(root: Any) -> str | None:
    operation = _enum_name(root.opcode)
    if operation == "power":
        return f"power {'on' if root.body.is_on else 'off'}"
    if operation == "brightness":
        return f"brightness {int(root.body.percent)}%"
    if operation == "multi_effect":
        return f"multi effect flag={int(root.body.flag)}"
    if operation != "multi":
        return None
    sub = _enum_name(root.body.sub)
    detail = root.body.sub_body
    if sub == "scene":
        return f"scene id={int(detail.code)}"
    if sub == "diy":
        return f"diy slot={int(detail.slot):#04x} type={int(detail.type_byte):#04x}"
    if sub == "music":
        colour = _rgb(detail.rgb) if detail.manual_color_count else "auto"
        return f"music {_named(detail.mode_id)} sensitivity={int(detail.sensitivity)} colour={colour}"
    if sub != "static":
        return None
    static_operation = int(detail.static_sub)
    body = detail.static_body
    if static_operation == 1:
        kelvin = int(body.kelvin)
        if kelvin:
            return f"colortemp {kelvin}K preview={_rgb(body.rgb_preview)} mask={_segment_mask(int(body.mask.bits))}"
        return f"color rgb={_rgb(body.rgb_direct)} mask={_segment_mask(int(body.mask.bits))}"
    if static_operation == 2:
        return f"brightness {int(body.percent)}% mask={_segment_mask(int(body.mask.bits))}"
    if static_operation == 3:
        shown = ",".join(
            f"s{index + 1}={int(percent)}" for index, percent in enumerate(body.segment_percent) if int(percent) != 100
        )
        return f"seg brightness all ({shown or 'all 100%'})"
    return None


def _format_h6199_command(root: Any) -> str | None:
    operation = _enum_name(root.opcode)
    if operation == "power":
        return f"power {'on' if root.body.is_on else 'off'}"
    if operation == "brightness":
        return f"brightness {int(root.body.percent)}%"
    if operation == "display_setting":
        setting = _enum_name(root.body.setting)
        if setting == "white_balance":
            payload = root.body.payload
            return f"white balance manual={int(payload.manual)} gains=({int(payload.red)},{int(payload.blue)})"
        if setting == "blank_screen":
            payload = root.body.payload
            return (
                f"blank screen {'on' if payload.is_on else 'off'} "
                f"detection={_named(payload.detection)} "
                f"low={int(payload.low_brightness_duration_seconds)}s "
                f"same={int(payload.same_tone_duration_seconds)}s"
            )
        return None
    if operation == "relative_brightness":
        body = root.body
        return (
            "relative brightness "
            f"left={int(body.left_percent)},top={int(body.top_percent)},"
            f"right={int(body.right_percent)},bottom={int(body.bottom_percent)}"
        )
    if operation != "mode":
        return None
    mode = _enum_name(root.body.sub_mode)
    detail = root.body.detail
    if mode == "scene":
        return f"scene id={int(detail.scene_id)} music={int(detail.music_code)}"
    if mode == "video":
        return (
            f"video region={_enum_name(detail.region)} source={_enum_name(detail.source)} "
            f"saturation={int(detail.saturation)} sound={bool(detail.sound_effects)} "
            f"softness={int(detail.softness)}"
        )
    if mode == "music":
        colour = _rgb(detail.fixed_colour) if detail.has_fixed_colour else "auto"
        return (
            f"music {_named(detail.mode)} sensitivity={int(detail.sensitivity)} "
            f"calm={bool(detail.is_calm)} colour={colour}"
        )
    if mode != "static_colour":
        return None
    operation = _enum_name(detail.operation)
    if operation == "colour":
        kelvin = int(detail.kelvin)
        if kelvin:
            return f"colortemp {kelvin}K preview={_rgb(detail.preview)} mask={_segment_mask(int(detail.segment_mask))}"
        rgb = f"({int(detail.red)},{int(detail.green)},{int(detail.blue)})"
        return f"color rgb={rgb} mask={_segment_mask(int(detail.segment_mask))}"
    if operation == "brightness":
        return f"brightness {int(detail.brightness_percent)}% mask={_segment_mask(int(detail.brightness_segment_mask))}"
    return None


def _format_h617a_status(root: Any) -> str | None:
    domain = _enum_name(root.domain)
    if domain == "power":
        return f"reply power={'on' if root.body.is_on else 'off'}"
    if domain == "brightness":
        return f"reply brightness={int(root.body.brightness_pct)}%"
    if domain in ("fw_version", "hw_version"):
        return f"reply {domain}={root.body.text!r}"
    if domain == "multi_effect":
        return f"reply multi_effect={int(root.body.flag)}"
    if domain == "segments":
        segments = " ".join(f"{int(item.brightness)}:{_rgb(item.colour)}" for item in root.body.segments)
        return f"reply segments group={int(root.body.group)} [{segments}]"
    if domain != "colormode":
        return None
    mode = _enum_name(root.body.mode)
    detail = root.body.mode_body
    if mode == "static":
        return f"reply colour_mode=static multi_effect={int(detail.sub)}"
    if mode == "scene":
        return f"reply colour_mode=scene id={int(detail.scene_id)}"
    if mode == "diy":
        return f"reply colour_mode=diy slot={int(detail.slot):#04x} type={int(detail.type_byte):#04x}"
    if mode == "music":
        colour = _rgb(detail.rgb) if detail.manual_color_count else "auto"
        return (
            f"reply colour_mode=music mode={_named(detail.mode_id)} "
            f"sensitivity={int(detail.sensitivity)} colour={colour}"
        )
    return None


def _format_h6199_status(root: Any) -> str | None:
    domain = _enum_name(root.domain)
    if domain == "power":
        return f"reply power={'on' if root.body.is_on else 'off'}"
    if domain == "brightness":
        return f"reply brightness={int(root.body.percent)}%"
    if domain in ("firmware", "hardware", "subordinate_20", "subordinate_21"):
        return f"reply {domain}={root.body.text!r}"
    if domain == "display_setting":
        setting = _enum_name(root.body.setting)
        if setting == "white_balance":
            payload = root.body.payload
            return (
                f"reply white_balance reset=({int(payload.reset_red)},{int(payload.reset_blue)}) "
                f"current=({int(payload.current_red)},{int(payload.current_blue)})"
            )
        if setting == "blank_screen":
            payload = root.body.payload
            return (
                f"reply blank_screen={'on' if payload.is_enabled else 'off'} "
                f"detection={_named(payload.detection)} "
                f"low={int(payload.low_brightness_duration_seconds)}s "
                f"same={int(payload.same_tone_duration_seconds)}s"
            )
        return None
    if domain == "relative_brightness":
        body = root.body
        return (
            "reply relative_brightness "
            f"left={int(body.left_percent)},top={int(body.top_percent)},"
            f"right={int(body.right_percent)},bottom={int(body.bottom_percent)}"
        )
    if domain == "segments":
        segments = " ".join(f"{int(item.brightness_percent)}:{_rgb(item.colour)}" for item in root.body.segments)
        return f"reply segments group={int(root.body.group)} [{segments}]"
    if domain != "colour_mode":
        return None
    mode = _enum_name(root.body.mode)
    detail = root.body.detail
    if mode == "static_colour":
        return "reply colour_mode=static"
    if mode == "scene":
        return f"reply colour_mode=scene id={int(detail.scene_id)}"
    if mode == "video":
        return (
            f"reply colour_mode=video region={_enum_name(detail.region)} source={_enum_name(detail.source)} "
            f"saturation={int(detail.saturation)} sound={bool(detail.sound_effects)} "
            f"softness={int(detail.softness)}"
        )
    if mode == "music":
        colour = _rgb(detail.fixed_colour) if detail.has_fixed_colour else "auto"
        return (
            f"reply colour_mode=music mode={int(detail.mode)} sensitivity={int(detail.sensitivity)} "
            f"calm={bool(detail.is_calm)} colour={colour}"
        )
    return None


def _describe_for_model(frame: bytes, direction: str, model: str) -> str | None:
    if frame[0] == 0x33:
        module, class_name, formatter = (
            ("h6199_command_write", "H6199CommandWrite", _format_h6199_command)
            if model == "H6199"
            else ("command_write", "CommandWrite", _format_h617a_command)
        )
        parsed = _read(module, class_name, frame)
        if parsed is None:
            return None
        if direction == "RX":
            operation = _enum_name(parsed.opcode)
            return f"ack {operation}" if operation is not None else None
        return formatter(parsed)
    if frame[0] != 0xAA:
        return None
    if direction == "TX":
        module, class_name = (
            ("h6199_status_query", "H6199StatusQuery") if model == "H6199" else ("status_query", "StatusQuery")
        )
        parsed = _read(module, class_name, frame)
        if parsed is None:
            return None
        domain = _enum_name(parsed.domain)
        if domain == "display_setting":
            return f"query {domain}.{_enum_name(parsed.body.setting)}"
        return f"query {domain}" if domain is not None else None
    module, class_name, formatter = (
        ("h6199_status_reply", "H6199StatusReply", _format_h6199_status)
        if model == "H6199"
        else ("status_reply", "StatusReply", _format_h617a_status)
    )
    parsed = _read(module, class_name, frame)
    return None if parsed is None else formatter(parsed)


def describe_generated(frame: bytes, direction: str, model: str = "auto") -> str | None:
    if direction not in ("TX", "RX"):
        raise ValueError(f"direction must be TX or RX, got {direction!r}")
    if len(frame) == 7:
        parsed = _read("music_stream", "MusicStream", frame, checksum="sum8")
        return None if parsed is None else f"mic-stream rgb={_rgb(parsed.colour)}"
    if len(frame) != FRAME_LENGTH:
        return None
    if frame[0] == 0xA1:
        parsed = _read("h6199_wifi_provision", "H6199WifiProvision", frame)
        return None if parsed is None else f"wifi-provision idx={int(parsed.index):#04x}"
    if frame[0] == 0xEE:
        parsed = _read("h6199_wifi_result", "H6199WifiResult", frame)
        return None if parsed is None else f"wifi-connect {_named(parsed.status)}"
    models = MODELS if model == "auto" else (model,)
    if any(candidate not in MODELS for candidate in models):
        raise ValueError(f"model must be one of {MODELS} or 'auto', got {model!r}")
    for candidate in models:
        if description := _describe_for_model(frame, direction, candidate):
            return description
    return None


def status_domain(frame: bytes, model: str = "H6199") -> int | None:
    module, class_name = (
        ("h6199_status_reply", "H6199StatusReply") if model == "H6199" else ("status_reply", "StatusReply")
    )
    parsed = _read(module, class_name, frame)
    return None if parsed is None else int(parsed.domain)


def is_wifi_provision(frame: bytes) -> bool:
    return _read("h6199_wifi_provision", "H6199WifiProvision", frame) is not None


def is_music_stream(frame: bytes) -> bool:
    return _read("music_stream", "MusicStream", frame, checksum="sum8") is not None
