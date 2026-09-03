"""H6179 command protocol vectors."""

from __future__ import annotations

import io
import os
import sys
from importlib import import_module
from typing import Any

import pytest
from kaitaistruct import KaitaiStream, KaitaiStructError

_GENERATED_DIR = os.environ.get("KAITAI_GENERATED_DIR")
if _GENERATED_DIR:
    sys.path.insert(0, _GENERATED_DIR)

_MODULE_NAME = (
    "h6179_command_write"
    if _GENERATED_DIR
    else "custom_components.ha_govee_led_ble.generated_protocol.h6179_command_write"
)
try:
    H6179CommandWrite = import_module(_MODULE_NAME).H6179CommandWrite
except ModuleNotFoundError as error:
    if error.name != _MODULE_NAME:
        raise
    pytest.skip("H6179 runtime generation is not integrated yet", allow_module_level=True)

H6179_VECTORS = {
    "power": bytes.fromhex("3301010000000000000000000000000000000033"),
    "raw brightness": bytes.fromhex("3304fe00000000000000000000000000000000c9"),
    "static RGB": bytes.fromhex("33050d0a141e000000000000000000000000003b"),
    "static temperature": bytes.fromhex("33050dffffff0e10ffcb8d000000000000000063"),
    "scene": bytes.fromhex("3305040700000000000000000000000000000035"),
    "music auto colour": bytes.fromhex("33050e006300000000000000000000000000005b"),
    "music fixed colour": bytes.fromhex("33050e013201123456000000000000000000007a"),
    "DIY": bytes.fromhex("33050a341200000000000000000000000000001a"),
}

WRONG_MODEL_VECTORS = {
    "H617A static": bytes.fromhex("330515010000000e10ffcb8dff7f000000000005"),
    "H6199 scene": bytes.fromhex("330504341278560000000000000000000000003a"),
}


def _parse(data: bytes) -> Any:
    stream = KaitaiStream(io.BytesIO(data))
    parsed = H6179CommandWrite(stream)
    parsed._read()
    assert stream.pos() == len(data)
    return parsed


def _round_trip(data: bytes) -> Any:
    parsed = _parse(data)
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(len(data))))
    parsed._write(output)
    assert output.to_byte_array() == data
    return parsed


def _frame(opcode: int, body: bytes) -> bytes:
    packet = bytes((0x33, opcode)) + body.ljust(17, b"\x00")
    checksum = 0
    for value in packet:
        checksum ^= value
    return packet + bytes((checksum,))


@pytest.mark.parametrize("frame", H6179_VECTORS.values(), ids=H6179_VECTORS)
def test_candidate_full_frame_vectors_round_trip(frame: bytes) -> None:
    _round_trip(frame)


def test_command_fields_preserve_h6179_semantics() -> None:
    power = _parse(H6179_VECTORS["power"])
    brightness = _parse(H6179_VECTORS["raw brightness"])
    rgb = _parse(H6179_VECTORS["static RGB"])
    temperature = _parse(H6179_VECTORS["static temperature"])
    scene = _parse(H6179_VECTORS["scene"])
    music_auto = _parse(H6179_VECTORS["music auto colour"])
    music_fixed = _parse(H6179_VECTORS["music fixed colour"])
    diy = _parse(H6179_VECTORS["DIY"])

    assert (power.opcode, power.body.is_on) == (0x01, 1)
    assert (brightness.opcode, brightness.body.raw) == (0x04, 0xFE)
    assert rgb.body.mode == 0x0D
    assert (
        rgb.body.payload.rgb_direct.red,
        rgb.body.payload.rgb_direct.green,
        rgb.body.payload.rgb_direct.blue,
    ) == (10, 20, 30)
    assert rgb.body.payload.kelvin == 0
    assert (
        temperature.body.payload.rgb_direct.red,
        temperature.body.payload.rgb_direct.green,
        temperature.body.payload.rgb_direct.blue,
        temperature.body.payload.kelvin,
        temperature.body.payload.rgb_preview.red,
        temperature.body.payload.rgb_preview.green,
        temperature.body.payload.rgb_preview.blue,
    ) == (255, 255, 255, 3600, 255, 203, 141)
    assert (scene.body.mode, scene.body.payload.scene_id) == (0x04, 7)
    assert (
        music_auto.body.mode,
        music_auto.body.payload.effect_id,
        music_auto.body.payload.sensitivity,
        music_auto.body.payload.colour_mode,
    ) == (0x0E, 0, 99, 0)
    assert not hasattr(music_auto.body.payload, "fixed_colour")
    assert (
        music_fixed.body.payload.effect_id,
        music_fixed.body.payload.sensitivity,
        music_fixed.body.payload.colour_mode,
        music_fixed.body.payload.fixed_colour.red,
        music_fixed.body.payload.fixed_colour.green,
        music_fixed.body.payload.fixed_colour.blue,
    ) == (1, 50, 1, 0x12, 0x34, 0x56)
    assert (diy.body.mode, diy.body.payload.diy_id) == (0x0A, 0x1234)


@pytest.mark.parametrize("frame", WRONG_MODEL_VECTORS.values(), ids=WRONG_MODEL_VECTORS)
def test_cross_model_bytes_round_trip_without_claiming_compatibility(frame: bytes) -> None:
    _round_trip(frame)


@pytest.mark.parametrize(
    "frame",
    [
        pytest.param(bytes.fromhex("3302010000000000000000000000000000000030"), id="unknown opcode"),
        pytest.param(bytes.fromhex("3301020000000000000000000000000000000030"), id="power value 2"),
        pytest.param(bytes.fromhex("3304130000000000000000000000000000000024"), id="brightness value 19"),
        pytest.param(bytes.fromhex("3304ff00000000000000000000000000000000c8"), id="brightness value 255"),
        pytest.param(bytes.fromhex("3305150000000000000000000000000000000023"), id="unknown mode"),
        pytest.param(bytes.fromhex("3305040600000000000000000000000000000034"), id="scene code 6"),
        pytest.param(bytes.fromhex("33050e0263000000000000000000000000000059"), id="music effect 2"),
        pytest.param(bytes.fromhex("33050e006400000000000000000000000000005c"), id="music sensitivity 100"),
        pytest.param(bytes.fromhex("33050e0063020000000000000000000000000059"), id="music colour mode 2"),
        pytest.param(bytes.fromhex("33050e006300123456000000000000000000002b"), id="automatic colour opaque bytes"),
        pytest.param(bytes.fromhex("3305040701000000000000000000000000000034"), id="non-zero opaque byte"),
    ],
)
def test_uncertain_values_and_opaque_bytes_round_trip(frame: bytes) -> None:
    _round_trip(frame)


@pytest.mark.parametrize("scene_code", [0x00, 0x06, 0x7F, 0xFF])
def test_scene_code_accepts_full_one_byte_catalogue_range(scene_code: int) -> None:
    parsed = _round_trip(_frame(0x05, bytes((0x04, scene_code))))
    assert parsed.body.payload.scene_id == scene_code


def test_unknown_opcode_and_mode_payloads_are_preserved() -> None:
    opcode_body = bytes.fromhex("102030405060708090a0b0c0d0e0f00102")
    opcode = _round_trip(_frame(0xA5, opcode_body))
    assert opcode.body == opcode_body

    mode_payload = bytes.fromhex("102030405060708090a0b0c0d0e0f001")
    mode = _round_trip(_frame(0x05, b"\x7f" + mode_payload))
    assert mode.body.payload == mode_payload


@pytest.mark.parametrize(
    "frame",
    [
        pytest.param(bytes.fromhex("3201010000000000000000000000000000000032"), id="wrong header"),
        pytest.param(bytes.fromhex("33010100000000000000000000000000000000"), id="truncated"),
    ],
)
def test_fixed_framing_is_rejected(frame: bytes) -> None:
    with pytest.raises(KaitaiStructError):
        _parse(frame)
