"""Semantic helpers over generated Kaitai protocol classes."""

from __future__ import annotations

import io
from importlib import import_module
from typing import Any, cast

from kaitaistruct import KaitaiStream, ReadWriteKaitaiStruct

CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.command_write").CommandWrite,
)
H6199CommandWrite = cast(
    Any,
    import_module("custom_components.ha_govee_led_ble.generated_protocol.h6199_command_write").H6199CommandWrite,
)


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


def _command_types(model: str) -> tuple[Any, Any, Any]:
    if model == "H6199":
        return (
            H6199CommandWrite,
            H6199CommandWrite.PowerBody,
            H6199CommandWrite.BrightnessBody,
        )
    return CommandWrite, CommandWrite.PowerCmd, CommandWrite.BrightnessCmd


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
