"""Representative checks for the generated Kaitai protocol parsers."""

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

_MODULE_PREFIX = "" if _GENERATED_DIR else "custom_components.ha_govee_led_ble.generated_protocol."


def _generated(module: str, class_name: str) -> type[Any]:
    return getattr(import_module(f"{_MODULE_PREFIX}{module}"), class_name)


CommandWrite = _generated("command_write", "CommandWrite")
StatusReply = _generated("status_reply", "StatusReply")
StatusQuery = _generated("status_query", "StatusQuery")
H6125BrightnessWrite = _generated("h6125_brightness_write", "H6125BrightnessWrite")
H6125ColourModeQuery = _generated("h6125_colour_mode_query", "H6125ColourModeQuery")
H6199StatusQuery = _generated("h6199_status_query", "H6199StatusQuery")
H6199StatusReply = _generated("h6199_status_reply", "H6199StatusReply")
DiyType03 = _generated("diy_type03", "DiyType03")
DiyType04 = _generated("diy_type04", "DiyType04")
H6199EffectUpload = _generated("h6199_effect_upload", "H6199EffectUpload")
WorkshopBody = _generated("workshop_body", "WorkshopBody")
SceneType1Body = _generated("scene_type1_body", "SceneType1Body")
SceneBody = _generated("scene_body", "SceneBody")
MusicBody = _generated("music_body", "MusicBody")
MusicStream = _generated("music_stream", "MusicStream")
H6199WifiBody = _generated("h6199_wifi_body", "H6199WifiBody")
H6199WifiProvision = _generated("h6199_wifi_provision", "H6199WifiProvision")
H6199WifiResult = _generated("h6199_wifi_result", "H6199WifiResult")

COMMAND_STATIC = bytes.fromhex("330515010000000e10ffcb8dff7f000000000005")
STATUS_SEGMENTS = bytes.fromhex("aaa50164ff880d64ff880d64ff880d0000000010")
H617A_SEGMENT_QUERY = bytes.fromhex("aaa505000000000000000000000000000000000a")
H6125_BRIGHTNESS = bytes.fromhex("3304fe00000000000000000000000000000000c9")
H6125_COLOUR_MODE_QUERY = bytes.fromhex("aa050100000000000000000000000000000000ae")
H6199_SEGMENT_QUERY = bytes.fromhex("aaa504000000000000000000000000000000000b")
TYPE03_PAINTED = bytes.fromhex(
    "0105030900640101010f01ff7f000001ff9a000101ffb0000201ffc3000301ffd4000401ffe3000501fff2000601ffff000701eeff000801dbff000901c6ff000a01adff000b0190ff000c0169ff000d0100ff000e"
)
TYPE04_FLAT = bytes.fromhex("0102040000640cff0000ff7d00ffff0000ff00000000000000000000000000000000")
TYPE04_COMBO = bytes.fromhex("010204ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff040000010000")
H6199_DIY = bytes.fromhex("01020400005c15ff0000ff7d00ffff0000ff000000ff00ffff8b00ff000000000000")
WORKSHOP = bytes.fromhex(
    "01030201200001000f1001ff000080141401801403ff00000000ff00ff00000080000080000000000000000000000000000000"
)
SCENE_TYPE1 = bytes.fromhex(
    "0103018306fff5000500ffffff0500ffe9ff0500ffffff0500ffe9d90500fff8ff060004ff1e00ff5a00ff3200ff7800000000"
)
SCENE_TYPE2 = bytes.fromhex(
    "01070203260001000a0201ff1901b40a0a02c8140500ff000000ffffffff0000ff00ff6b140196000000002300020f050201ff1401fb000001fa0a0400fffb00ff4b4747ff00ff1b000000000000001a000000010201ff0501c8141402ee140100ffff0000000000000000000000000000000000000000"
)
MUSIC_BODY = bytes.fromhex("0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000")
MUSIC_STREAM = bytes.fromhex("a5028356000080")
WIFI_BODY = bytes.fromhex(
    "0746414b454e4554083132333435363738000a0000001868747470733a2f2f6465766963652e676f7665652e636f6d0000"
)
WIFI_PROVISION = bytes.fromhex("a111010746414b454e45540831323334353637d8")
WIFI_RESULT_SUCCESS = bytes.fromhex("ee110000000000000000000000000000000000ff")
WIFI_RESULT_FAILURE = bytes.fromhex("ee110100000000000000000000000000000000fe")


def _parse(root_type: type[Any], data: bytes) -> Any:
    stream = KaitaiStream(io.BytesIO(data))
    parsed = root_type(stream)
    parsed._read()
    assert stream.pos() == len(data)
    return parsed


REPRESENTATIVE_ROOTS = (
    pytest.param(CommandWrite, COMMAND_STATIC, id="H617A command"),
    pytest.param(StatusReply, STATUS_SEGMENTS, id="H617A status"),
    pytest.param(StatusQuery, H617A_SEGMENT_QUERY, id="H617A segment query"),
    pytest.param(H6125BrightnessWrite, H6125_BRIGHTNESS, id="H6125 brightness"),
    pytest.param(H6125ColourModeQuery, H6125_COLOUR_MODE_QUERY, id="H6125 colour-mode query"),
    pytest.param(H6199StatusQuery, H6199_SEGMENT_QUERY, id="H6199 segment query"),
    pytest.param(DiyType03, TYPE03_PAINTED, id="Type03 painted"),
    pytest.param(DiyType04, TYPE04_FLAT, id="Type04 flat"),
    pytest.param(DiyType04, TYPE04_COMBO, id="Type04 combo"),
    pytest.param(H6199EffectUpload, H6199_DIY, id="H6199 DIY effect"),
    pytest.param(WorkshopBody, WORKSHOP, id="Workshop"),
    pytest.param(SceneType1Body, SCENE_TYPE1, id="scene type 1"),
    pytest.param(SceneBody, SCENE_TYPE2, id="scene type 2"),
    pytest.param(MusicBody, MUSIC_BODY, id="music body"),
    pytest.param(MusicStream, MUSIC_STREAM, id="music stream"),
    pytest.param(H6199WifiBody, WIFI_BODY, id="Wi-Fi body"),
    pytest.param(H6199WifiProvision, WIFI_PROVISION, id="Wi-Fi provision"),
    pytest.param(H6199WifiResult, WIFI_RESULT_SUCCESS, id="Wi-Fi result"),
)


@pytest.mark.parametrize(("root_type", "data"), REPRESENTATIVE_ROOTS)
def test_representative_roots_round_trip_and_consume_input(root_type: type[Any], data: bytes) -> None:
    parsed = _parse(root_type, data)
    parsed._fetch_instances()
    parsed._check()

    output = KaitaiStream(io.BytesIO(bytes(len(data))))
    parsed._write(output)

    assert output.to_byte_array() == data


def test_command_and_status_fields_are_meaningful() -> None:
    command = _parse(CommandWrite, COMMAND_STATIC)
    assert command.opcode.name == "multi"
    assert command.body.sub.name == "static"
    assert command.body.sub_body.static_sub == 1
    assert command.body.sub_body.static_body.kelvin == 3600
    assert (
        command.body.sub_body.static_body.rgb_preview.red,
        command.body.sub_body.static_body.rgb_preview.green,
        command.body.sub_body.static_body.rgb_preview.blue,
    ) == (255, 203, 141)

    status = _parse(StatusReply, STATUS_SEGMENTS)
    assert status.domain.name == "segments"
    assert status.body.group == 1
    assert [
        (segment.brightness, segment.colour.red, segment.colour.green, segment.colour.blue)
        for segment in status.body.segments
    ] == [(100, 255, 136, 13)] * 3

    h617a_query = _parse(StatusQuery, H617A_SEGMENT_QUERY)
    h6125_brightness = _parse(H6125BrightnessWrite, H6125_BRIGHTNESS)
    h6125_colour_mode = _parse(H6125ColourModeQuery, H6125_COLOUR_MODE_QUERY)
    h6199_query = _parse(H6199StatusQuery, H6199_SEGMENT_QUERY)
    assert (h617a_query.domain.name, h617a_query.body.group) == ("segments", 5)
    assert h6125_brightness.value == 0xFE
    assert h6125_colour_mode.header == b"\xaa\x05\x01"
    assert (h6199_query.domain.name, h6199_query.body.group) == ("segments", 4)


def test_diy_shapes_expose_painted_flat_and_combo_fields() -> None:
    painted = _parse(DiyType03, TYPE03_PAINTED)
    assert painted.effect.name == "clockwise"
    assert (painted.speed, painted.brightness, painted.num_groups) == (0, 100, 15)
    assert painted.groups[-1].segment_indices == [14]

    flat = _parse(DiyType04, TYPE04_FLAT)
    assert (flat.family, flat.body.variant, flat.body.speed, flat.body.len_palette) == (0, 0, 100, 12)
    assert [(colour.red, colour.green, colour.blue) for colour in flat.body.palette.colours] == [
        (255, 0, 0),
        (255, 125, 0),
        (255, 255, 0),
        (0, 255, 0),
    ]

    combo = _parse(DiyType04, TYPE04_COMBO)
    assert (combo.family, combo.body.seqlen) == (255, 4)
    assert [(pair.family, pair.variant) for pair in combo.body.pairs] == [(0, 0), (1, 0)]


def test_effect_workshop_and_scene_fields_preserve_structure() -> None:
    effect = _parse(H6199EffectUpload, H6199_DIY)
    assert (effect.chunk_count, effect.kind.name) == (2, "diy")
    assert (effect.content.family, effect.content.variant, effect.content.speed) == (0, 0, 92)
    assert (effect.content.palette_len, len(effect.content.palette), len(effect.content.padding)) == (21, 7, 6)

    workshop = _parse(WorkshopBody, WORKSHOP)
    layer = workshop.layers[0]
    assert (workshop.header.linecount, workshop.num_layers, layer.len_body) == (3, 1, 32)
    assert layer.body.select_type.name == "select_ic_continuously"
    assert [(colour.red, colour.green, colour.blue) for colour in layer.body.palette] == [
        (255, 0, 0),
        (0, 0, 255),
        (0, 255, 0),
    ]

    type1 = _parse(SceneType1Body, SCENE_TYPE1)
    assert (type1.scene_type, type1.layout, type1.colour_stride, type1.brightness_flag) == (1, 0, 3, True)
    assert (type1.num_steps, type1.num_palette, len(type1.padding)) == (6, 4, 3)

    type2 = _parse(SceneBody, SCENE_TYPE2)
    assert (type2.scene_type.name, type2.num_records) == ("scene_v2", 3)
    assert [record.len_body for record in type2.records] == [38, 35, 26]
    assert [record.body.num_palette for record in type2.records] == [5, 4, 1]


def test_music_and_wifi_result_fields_preserve_semantics() -> None:
    body = _parse(MusicBody, MUSIC_BODY)
    assert (body.command, body.mode.name, body.num_palette) == (b"A", "bloom", 7)
    assert (body.tail.style_companion, body.tail_len, len(body.padding)) == (20, 2, 6)

    stream = _parse(MusicStream, MUSIC_STREAM)
    assert (stream.colour.red, stream.colour.green, stream.colour.blue) == (86, 0, 0)
    assert stream.checksum == stream.checksum_expected == 128

    wifi_body = _parse(H6199WifiBody, WIFI_BODY)
    assert (wifi_body.ssid, wifi_body.password) == ("FAKENET", "12345678")
    assert (wifi_body.tz_hour, wifi_body.api) == (10, "https://device.govee.com")

    provision = _parse(H6199WifiProvision, WIFI_PROVISION)
    assert (provision.index, provision.is_header, provision.is_terminator) == (1, False, False)

    success = _parse(H6199WifiResult, WIFI_RESULT_SUCCESS)
    failure = _parse(H6199WifiResult, WIFI_RESULT_FAILURE)
    assert success.status.name == "associated"
    assert failure.status.name == "not_connected"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(COMMAND_STATIC, id="command XOR"),
        pytest.param(STATUS_SEGMENTS, id="status XOR"),
        pytest.param(WIFI_RESULT_SUCCESS, id="Wi-Fi result XOR"),
    ],
)
def test_xor_checksum_families(data: bytes) -> None:
    checksum = 0
    for value in data[:-1]:
        checksum ^= value
    assert checksum == data[-1]


def test_sum8_checksum_family() -> None:
    assert sum(MUSIC_STREAM[:-1]) & 0xFF == MUSIC_STREAM[-1]


REJECTED_ROOTS = (
    pytest.param(
        DiyType04,
        "010204010064048b00ff000000000000000000000000000000000000000000000000",
        id="odd Type04 palette length",
    ),
    pytest.param(
        DiyType04,
        "010204ff003315ff0000ff7f00ffff0000ff000000ff00ffff8b00ff030000000000",
        id="odd Type04 combo sequence length",
    ),
    pytest.param(
        H6199EffectUpload,
        "01020404073213ff0000ff7d00ffff0000ff000000ff00ffff000000000000000000",
        id="odd H6199 DIY palette length",
    ),
    pytest.param(
        StatusReply,
        "aaa506731f646408646464fe6464640000000093",
        id="invalid H617A segment group",
    ),
    pytest.param(
        H6199WifiProvision,
        "a1120004000000000000000000000000000000b7",
        id="invalid Wi-Fi provision sub-opcode",
    ),
    pytest.param(
        H6199WifiResult,
        "ee120000000000000000000000000000000000fc",
        id="invalid Wi-Fi result sub-opcode",
    ),
    pytest.param(
        H6199StatusReply,
        "aaa505000000000000000000000000000000000a",
        id="invalid H6199 segment group",
    ),
)


@pytest.mark.parametrize(("root_type", "raw_hex"), REJECTED_ROOTS)
def test_critical_invalid_shapes_are_rejected(root_type: type[Any], raw_hex: str) -> None:
    with pytest.raises(KaitaiStructError):
        _parse(root_type, bytes.fromhex(raw_hex))
