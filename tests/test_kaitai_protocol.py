"""Representative checks for the generated Kaitai protocol parsers."""

from __future__ import annotations

import io
import os
import sys
from dataclasses import replace
from importlib import import_module
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoredExtraData
from kaitaistruct import KaitaiStream, KaitaiStructError

from custom_components.ha_govee_led_ble import generated_protocol_adapter
from custom_components.ha_govee_led_ble.const import (
    MODEL_PROFILES,
    UNSUPPORTED_PROFILE,
    ModelProfile,
    ReadDomain,
    get_profile,
)
from custom_components.ha_govee_led_ble.coordinator import GoveeBLECoordinator
from custom_components.ha_govee_led_ble.coordinator_expectations import expectations_from_packet
from custom_components.ha_govee_led_ble.coordinator_status import ParsedMode, parse_color_mode
from custom_components.ha_govee_led_ble.generated_protocol_adapter import ProtocolParseRejection
from custom_components.ha_govee_led_ble.light import GoveeBLELight
from custom_components.ha_govee_led_ble.light_commands import build_color_rgb, build_color_temp, kelvin_to_rgb
from custom_components.ha_govee_led_ble.transport import WRITE_UUID, xor_checksum

_GENERATED_DIR = os.environ.get("KAITAI_GENERATED_DIR")
if _GENERATED_DIR:
    sys.path.insert(0, _GENERATED_DIR)

_MODULE_PREFIX = "" if _GENERATED_DIR else "custom_components.ha_govee_led_ble.generated_protocol."


def _generated(module: str, class_name: str) -> type[Any]:
    return getattr(import_module(f"{_MODULE_PREFIX}{module}"), class_name)


CommandWrite = _generated("command_write", "CommandWrite")
StatusReply = _generated("status_reply", "StatusReply")
StatusQuery = _generated("status_query", "StatusQuery")
H6199StatusQuery = _generated("h6199_status_query", "H6199StatusQuery")
H6199StatusReply = _generated("h6199_status_reply", "H6199StatusReply")
H6199CommandAck = _generated("h6199_command_ack", "H6199CommandAck")
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
H6199_SEGMENT_QUERY = bytes.fromhex("aaa504000000000000000000000000000000000b")
H6199_POWER_ACK = bytes.fromhex("3301000000000000000000000000000000000032")
H6199_MODE_ACK = bytes.fromhex("3305000000000000000000000000000000000036")
H6199_DISPLAY_ACK = bytes.fromhex("33a900000000000000000000000000000000009a")
H6199_RELATIVE_BRIGHTNESS_ACK = bytes.fromhex("33ae00000000000000000000000000000000009d")
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


@pytest.mark.parametrize("selector", [0, 1])
def test_shared_colour_mode_query_selectors(selector: int) -> None:
    packet = generated_protocol_adapter.build_colour_mode_query(selector=selector)
    parsed = _parse(StatusQuery, packet)
    assert parsed.domain.name == "colour_mode" and parsed.body.selector == selector
    assert parsed.body.zeros == [0] * 16


def test_h617a_direct_register_replay_not_app_captures(hass) -> None:
    """H617A HW 3.01.01/FW 3.02.24, direct queries on 2026-09-16."""
    coordinator = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H617A", configuration_url=None)
    coordinator.install_static_color(kelvin=4000)
    static = bytes.fromhex("aa051500000000000000000000000000000000ba")
    detail = _parse(StatusReply, static).body.mode_body
    assert detail.kelvin == 0 and detail.unknown_tail == bytes(13)
    coordinator._notify_callback(None, bytearray(static))
    # Both AA0500 and AA0501 returned this mode-only reply after a 4000 K write.
    pages = [
        "aaa501640000ff64ffcda664ffcda60000000095",
        "aaa50264ffcda664ffcda664ffcda600000000fd",
        "aaa50364ffcda664ffcda664ffcda600000000fc",
        "aaa50464ffcda664ffcda664ffcda600000000fb",
        "aaa50564ffcda664ffcda664ffcda600000000fa",
    ]
    for first, expected in (
        (pages[0], (0, 0, 255)),
        ("aaa50164ffb96964ffcda664ffcda60000000045", (255, 185, 105)),
    ):
        for raw in (first, *pages[1:]):
            packet = bytes.fromhex(raw)
            assert xor_checksum(packet) == 0
            coordinator._notify_callback(None, bytearray(packet))
        assert coordinator.segment_colors == [expected] + [(255, 205, 166)] * 14
        assert coordinator.segment_brightness == [100] * 15
        assert coordinator.segment_state_source == "observed"

    for raw, mode in (
        ("aa0513043200012060a00000000000000000006b", "spectrum"),
        ("aa0513063200012060a000000000000000000069", "rolling"),
    ):
        packet = bytes.fromhex(raw)
        assert xor_checksum(packet) == 0
        parsed = parse_color_mode(_parse(StatusReply, packet), "H617A")
        assert parsed.music_mode == mode
        assert parsed.music_sensitivity == 50
        assert parsed.music_color == (32, 96, 160)

    count = _parse(StatusReply, bytes.fromhex("aa0f0f00000000000000000000000000000000aa"))
    assert count.domain == 0x0F and count.body.light_count == 15
    assert count.body.is_valid and count.body.unknown == bytes(16)
    # The count reply is currently raw/unnamed, not a physical-IC observation.


def test_h617a_apk_schema_counterexamples_are_synthetic() -> None:
    """Document current parser limits, without claiming these replies occurred live."""
    query = _parse(StatusQuery, bytes.fromhex("aa050100000000000000000000000000000000ae"))
    assert query.body.selector == 1
    hopping = _parse(MusicBody, bytes.fromhex("0102413301ff0000ff0000326101030206"))
    assert hopping.tail.speed == 0x61
    assert (hopping.tail.piece_length_min, hopping.tail.piece_length_max) == (1, 3)
    assert (hopping.tail.piece_count_min, hopping.tail.piece_count_max) == (2, 6)
    piano = _parse(MusicBody, bytes.fromhex("0102413401ff0000000f0b0407"))
    assert (piano.tail.gradient, piano.tail.key_count, piano.tail.speed) == (0, 15, 11)
    assert (piano.tail.off_minimum, piano.tail.off_maximum) == (4, 7)
    # New music reads ID/sensitivity only; the synthetic suffix stays opaque.
    music = _parse(StatusReply, bytes.fromhex("aa0513303200012060a00000000000000000005f"))
    selector = music.body.mode_body
    assert selector.mode_id.name == "bloom" and selector.sensitivity == 50
    assert not selector.is_legacy
    assert not hasattr(selector, "has_fixed_colour") and not hasattr(selector, "rgb")
    assert music.body._raw_mode_body[2:] == bytes.fromhex("00012060a0000000000000000000")
    parsed = parse_color_mode(music, "H617A")
    assert parsed.music_color is None and not parsed.music_color_present and parsed.music_calm is None
    # A real successful ordinary ACK parses as a write, but is never state evidence.
    ack = _parse(CommandWrite, H6199_POWER_ACK)
    assert ack.body.is_on == 0
    flat = _parse(DiyType04, bytes.fromhex("01020401003203ff000000"))
    assert flat.body.padding == [0]  # APK names this octet as empty sequence length.


def test_h6199_direct_register_extensions_not_app_captures() -> None:
    diy = _parse(H6199StatusReply, bytes.fromhex("aa050afe0000000000000000000000000000005b"))
    assert diy.body.mode.name == "diy" and diy.body.detail.code == 254
    static = _parse(H6199StatusReply, bytes.fromhex("aa051501000000000000000000000000000000bb"))
    assert static.body.detail.gradient == 1
    for raw, domain, value in (
        ("aa3001000000000000000000000000000000009b", "strip_direction", 1),
        ("aa3101000000000000000000000000000000009a", "camera_position", 1),
        ("aa32010000000000000000000000000000000099", "camera_status", 1),
        ("aaa3010000000000000000000000000000000008", "gradient", 1),
    ):
        packet = bytes.fromhex(raw)
        assert xor_checksum(packet[:-1]) == packet[-1]
        parsed = _parse(H6199StatusReply, packet)
        assert parsed.domain.name == domain and parsed.body.value == value
    for raw, opcode in (
        ("3330000000000000000000000000000000000003", "strip_direction"),
        ("3331000000000000000000000000000000000002", "camera_position"),
        ("33a3000000000000000000000000000000000090", "gradient"),
    ):
        assert _parse(H6199CommandAck, bytes.fromhex(raw)).opcode.name == opcode


@pytest.fixture
def static_coordinator(hass, monkeypatch):
    if not _GENERATED_DIR:
        pytest.skip("Synthetic static layout is an all-schema fixture, not a runtime root")
    schema = "synthetic_static_status_reply"
    monkeypatch.setitem(
        generated_protocol_adapter._STATUS_ROOTS,
        "test-static",
        (schema, _generated(schema, "SyntheticStaticStatusReply")),
    )
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H7001",
        ModelProfile(
            "Synthetic static colour fixture",
            command_grammar="H617A",
            status_grammar="test-static",
            read_domains=frozenset({ReadDomain.COLOUR_MODE, ReadDomain.SEGMENTS}),
            supports_rgb=True,
            supports_color_temperature=True,
            static_readback_echoes_color=True,
            static_readback_kelvin=True,
            segment_count=15,
            segment_group_size=3,
            supports_segment_writes=True,
            whole_device_mask=0x7FFF,
        ),
    )
    return GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", "H7001", configuration_url=None)


def _static_reply(*, rgb=None, kelvin=None):
    payload = bytes((0xAA, 5, 0x15, int(rgb is not None) | (int(kelvin is not None) << 1)))
    if rgb is not None:
        payload += bytes(rgb)
    if kelvin is not None:
        payload += kelvin.to_bytes(2, "little")
    payload = payload.ljust(19, b"\x00")
    return bytearray(payload + bytes((xor_checksum(payload),)))


def _static_segments(coordinator, rgb):
    for group in range(1, 6):
        payload = bytes((0xAA, 0xA5, group, *([100, *rgb] * 3))).ljust(19, b"\x00")
        coordinator._notify_callback(None, bytearray(payload + bytes((xor_checksum(payload),))))


def _static_scene_reply():
    payload = bytes.fromhex("aa0504e8fd").ljust(19, b"\x00")
    return bytearray(payload + bytes((xor_checksum(payload),)))


@pytest.mark.parametrize("method", ["refresh", "observe"])
@pytest.mark.parametrize("kelvin", [None, 4200])
@pytest.mark.parametrize("return_static", [False, True])
async def test_static_verification_rejects_newer_mode(static_coordinator, method, kelvin, return_static):
    coord = static_coordinator
    field = "rgb_color" if kelvin is None else "color_temp_kelvin"
    value = (1, 2, 3) if kelvin is None else kelvin

    async def write(_uuid, _packet, **_kwargs):
        coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=kelvin))
        coord._notify_callback(None, _static_scene_reply())
        if return_static:
            coord._notify_callback(None, _static_reply())

    coord._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    if method == "refresh":
        assert await coord.refresh_state(**{f"expected_{field}": value}, timeout=0.01) is False
    else:
        assert await coord.async_observe_effect({field: value}, timeout=0.01) is not True
    assert not coord._expected_state
    assert coord.color_mode is (ParsedMode.COLOUR if return_static else ParsedMode.SCENE)

    async def current_write(_uuid, _packet, **_kwargs):
        coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=kelvin))

    coord._client.write_gatt_char.side_effect = current_write
    if method == "refresh":
        assert await coord.refresh_state(**{f"expected_{field}": value}, timeout=0.01) is True
    else:
        assert await coord.async_observe_effect({field: value}, timeout=0.01) is True


@pytest.mark.parametrize("rgb", [(1, 2, 3), kelvin_to_rgb(4200)])
def test_static_mode_roundtrip_releases_historical_authority(static_coordinator, rgb):
    coord = static_coordinator
    light = GoveeBLELight(coord)
    coord._notify_callback(None, _static_reply(kelvin=4200))
    coord._notify_callback(None, _static_scene_reply())
    assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "retained"
    coord._notify_callback(None, _static_reply())
    _static_segments(coord, rgb)
    assert coord.rgb_color == rgb and coord.rgb_color_source == "segment"
    assert coord._field_revisions["color_temp_kelvin"] == 1
    assert light.color_mode is (ColorMode.COLOR_TEMP if rgb == kelvin_to_rgb(4200) else ColorMode.RGB)


def test_static_mode_only_repeat_keeps_current_direct_precedence(static_coordinator):
    coord = static_coordinator
    coord._notify_callback(None, _static_reply(kelvin=4200))
    coord._notify_callback(None, _static_reply())
    _static_segments(coord, (1, 2, 3))
    assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "observed"
    assert coord._field_revisions["color_temp_kelvin"] == 1


@pytest.mark.parametrize(
    ("model", "frame"),
    [
        ("H617A", "aa05049d0800000000000000000000000000003e"),
        ("H617A", "aa050a2003000000000000000000000000000086"),
        ("H617A", "aa051303580100000000000000000000000000e6"),
        ("H6199", "aa050000012a01370000000000000000000000b2"),
    ],
)
def test_every_nonstatic_notification_demotes_direct_authority(static_coordinator, model, frame):
    coord = static_coordinator
    coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=4200))
    coord.model, coord.profile = model, MODEL_PROFILES[model]
    coord._notify_callback(None, bytearray.fromhex(frame))
    assert coord.color_mode is not ParsedMode.COLOUR
    assert coord.rgb_color_source == coord.color_temp_kelvin_source == "retained"
    assert coord.rgb_color == (1, 2, 3) and coord.color_temp_kelvin == 4200
    assert coord._field_revisions["rgb_color"] == coord._field_revisions["color_temp_kelvin"] == 1


def test_local_mode_command_releases_direct_authority(static_coordinator):
    coord = static_coordinator
    coord._notify_callback(None, _static_reply(kelvin=4200))
    coord._arm_expected(generated_protocol_adapter.build_h617a_scene(65000))
    assert coord.color_temp_kelvin_source == "retained" and coord.color_temp_kelvin == 4200
    coord._expected_state.clear()
    coord._notify_callback(None, _static_reply())
    _static_segments(coord, (1, 2, 3))
    assert coord.color_temp_kelvin is None and coord.rgb_color == (1, 2, 3)


@pytest.mark.parametrize(
    ("model", "frame"),
    [
        ("H617A", "aa05049d0800000000000000000000000000003e"),
        ("H617A", "aa051303580100000000000000000000000000e6"),
        ("H6199", "aa050000012a01370000000000000000000000b2"),
    ],
)
async def test_static_failure_never_restores_stale_mode_siblings(hass, model, frame):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    coord.is_on = True
    coord._notify_callback(None, bytearray.fromhex(frame))
    assert coord.active_mode != "colour"

    async def send(_packet):
        coord._notify_callback(None, bytearray.fromhex("aa051501000000000000000000000000000000bb"))
        raise RuntimeError("failed with fresh static mode")

    coord.send_command = AsyncMock(side_effect=send)
    with pytest.raises(HomeAssistantError):
        await GoveeBLELight(coord).async_turn_on(rgb_color=(1, 2, 3))
    assert coord.active_mode == "colour" and coord.color_mode is ParsedMode.COLOUR
    assert coord.effect is None and coord.scene_code is None and coord.diy_code is None
    assert coord.music_mode == coord.video_mode == "off"


@pytest.mark.parametrize("fail", [False, True])
async def test_clear_effect_preserves_newer_scene_notification(static_coordinator, fail):
    coord = static_coordinator
    coord.is_on = True
    light = GoveeBLELight(coord)

    async def send(_packet):
        coord._notify_callback(None, _static_scene_reply())
        if fail:
            raise RuntimeError("effect-off write failed")

    coord.send_command = AsyncMock(side_effect=send)
    if fail:
        with pytest.raises(HomeAssistantError), light._rollback():
            await light._async_clear_effect()
    else:
        await light._async_clear_effect()
    assert coord.color_mode is ParsedMode.SCENE and coord.scene_code == 65000
    assert coord.active_mode == "scene"


@pytest.mark.parametrize("model", ["H617A", "H7001"])
@pytest.mark.parametrize("kelvin", [None, 4200])
@pytest.mark.parametrize("new_reply", ["none", "static", "scene", "segments", "partial_segments"])
async def test_static_failure_rolls_back_coherent_state(static_coordinator, model, kelvin, new_reply):
    coord = static_coordinator
    coord.model, coord.profile = model, MODEL_PROFILES[model]
    coord.is_on = True
    coord._notify_callback(None, _static_scene_reply())
    _static_segments(coord, (9, 8, 7))
    coord._segment_groups_observed.add(1)
    coord._segment_query_colors = list(coord.segment_colors)
    coord._segment_query_brightness = list(coord.segment_brightness)
    before = (coord.segment_state_observed_at, set(coord._segment_groups_observed), list(coord._segment_query_colors))
    light = GoveeBLELight(coord)

    async def send(_packet):
        if new_reply == "static":
            coord._notify_callback(None, _static_reply(rgb=(1, 2, 3)) if model == "H7001" else _static_reply())
        elif new_reply == "scene":
            coord._notify_callback(None, _static_scene_reply())
        elif new_reply == "segments":
            _static_segments(coord, (4, 5, 6))
        elif new_reply == "partial_segments":
            coord._notify_callback(None, bytearray.fromhex("aaa50164ff880d64ff880d64ff880d0000000010"))
        raise RuntimeError("static write failed")

    coord.send_command = AsyncMock(side_effect=send)
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(**({"rgb_color": (1, 2, 3)} if kelvin is None else {"color_temp_kelvin": kelvin}))
    if new_reply == "none":
        assert coord.active_mode == "scene" and coord.color_mode is ParsedMode.SCENE and coord.scene_code == 65000
        assert coord.segment_state_source == "observed" and coord.segment_colors == [(9, 8, 7)] * 15
        assert (coord.segment_state_observed_at, coord._segment_groups_observed, coord._segment_query_colors) == before
    elif new_reply in {"scene", "segments", "partial_segments"}:
        assert coord.active_mode == "scene" and coord.scene_code == 65000
        if new_reply == "segments":
            assert coord.segment_colors == [(4, 5, 6)] * 15 and coord.segment_state_source == "observed"
        elif new_reply == "partial_segments":
            assert coord.segment_colors == [(9, 8, 7)] * 15 and coord.segment_state_source == "observed"
            assert coord.segment_state_observed_at == before[0]
            assert coord._segment_groups_observed == {1}
            assert coord._segment_query_colors[:3] == [(255, 136, 13)] * 3
    else:
        assert coord.active_mode == "colour" and coord.color_mode is ParsedMode.COLOUR and coord.scene_code is None
        assert coord.effect is None and coord.music_mode == coord.video_mode == "off"


def test_static_direct_notification_provenance_and_projection(static_coordinator):
    coord = static_coordinator
    coord.is_on = True
    light = GoveeBLELight(coord)
    rgb = kelvin_to_rgb(4200)
    frame = _static_reply(rgb=rgb, kelvin=4200)
    parsed = generated_protocol_adapter.parse_status_result(bytes(frame), coord.model)
    assert parse_color_mode(parsed.parsed, coord.model).color_temp_kelvin == 4200
    coord._notify_callback(None, frame)
    assert coord.rgb_color == rgb and coord.color_temp_kelvin == 4200
    assert coord.rgb_color_source == coord.color_temp_kelvin_source == "observed"
    assert coord._field_revisions["rgb_color"] == coord._field_revisions["color_temp_kelvin"] == 1
    assert light.color_mode is ColorMode.COLOR_TEMP and light.color_temp_kelvin == 4200
    assert light.state_attributes["color_mode"] is ColorMode.COLOR_TEMP
    _static_segments(coord, (1, 2, 3))
    assert coord.segment_state_source == "observed"
    assert coord.rgb_color == rgb and coord.color_temp_kelvin == 4200
    coord._notify_callback(None, _static_reply(rgb=rgb))
    assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "retained"
    assert coord._field_revisions["color_temp_kelvin"] == 1
    coord._notify_callback(None, _static_reply(rgb=(1, 2, 3)))
    assert coord.color_temp_kelvin is None and coord.color_temp_kelvin_source == "initial"
    assert coord._field_revisions["color_temp_kelvin"] == 1
    assert light.color_mode is ColorMode.RGB and light.rgb_color == (1, 2, 3)
    assert light.state_attributes["color_mode"] is ColorMode.RGB
    coord._notify_callback(None, _static_reply(kelvin=5000))
    assert light.color_mode is ColorMode.COLOR_TEMP and light.color_temp_kelvin == 5000


@pytest.mark.parametrize("kelvin", [None, 4200])
async def test_static_verification_needs_fresh_accepted_fields(static_coordinator, kelvin):
    coord = static_coordinator
    rgb = (1, 2, 3) if kelvin is None else None
    field = "rgb_color" if rgb is not None else "color_temp_kelvin"
    value = rgb if rgb is not None else kelvin
    coord.install_static_color(rgb=rgb, kelvin=kelvin)
    coord._arm_expected(build_color_rgb(*rgb, coord.model) if rgb else build_color_temp(kelvin, coord.model))
    coord._client = MagicMock(is_connected=True)
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    frame = _static_reply(rgb=(9, 8, 7), kelvin=2000)

    async def query(**kwargs):
        assert kwargs["query_color_mode"]
        coord._notify_callback(None, frame)
        return True

    coord._send_state_queries = AsyncMock(side_effect=query)
    assert await coord.async_observe_effect({field: value}, timeout=0.001) is None
    assert field not in coord._field_revisions
    frame = _static_reply()
    assert not await coord.refresh_state(**{f"expected_{field}": value}, timeout=0.001)
    frame = _static_reply(rgb=rgb, kelvin=kelvin)
    assert await coord.refresh_state(**{f"expected_{field}": value}, timeout=0.01)
    assert await coord.async_observe_effect({field: value}, timeout=0.01) is True
    revision = coord._field_revisions[field]
    coord._notify_callback(None, _static_reply(rgb=(9, 8, 7), kelvin=2000))
    assert coord._field_revisions[field] == revision and getattr(coord, field) == value
    coord._expected_state.clear()
    frame = _static_reply(rgb=(9, 8, 7), kelvin=2000)
    assert await coord.async_observe_effect({field: value}, timeout=0.01) is False


@pytest.mark.parametrize("during", ["before", "state", "extra", "segments"])
@pytest.mark.parametrize("observation", ["rgb", "kelvin", "segments", "mode"])
async def test_static_restore_cannot_overwrite_notifications(static_coordinator, during, observation):
    coord = static_coordinator
    light = GoveeBLELight(coord)
    stored = {
        "color_mode": ColorMode.COLOR_TEMP,
        "color_temp_kelvin": 4200,
        "segment_colors": [[4, 5, 6]] * 15,
        "segment_brightness": [50] * 15,
    }

    def notify():
        if observation == "segments":
            coord.color_mode = ParsedMode.COLOUR
            _static_segments(coord, (1, 2, 3))
        elif observation == "mode":
            coord.color_mode = ParsedMode.MUSIC
        else:
            coord._notify_callback(
                None, _static_reply(rgb=(1, 2, 3)) if observation == "rgb" else _static_reply(kelvin=5000)
            )

    async def state():
        if during in {"state", "segments"}:
            notify()
        return SimpleNamespace(attributes={} if during == "extra" else stored)

    async def extra():
        notify()
        return RestoredExtraData(stored)

    light.async_get_last_state = AsyncMock(side_effect=state)
    light.async_get_last_extra_data = AsyncMock(side_effect=extra)
    if during == "before":
        notify()
    if during != "segments":
        await light._async_restore_static_color()
    await light._async_restore_segments()
    assert coord.color_temp_kelvin != 4200
    assert coord.segment_state_source != "restored"
    if observation == "rgb":
        assert light.rgb_color == (1, 2, 3) and light.color_mode is ColorMode.RGB
    elif observation == "kelvin":
        assert light.color_temp_kelvin == 5000 and light.color_mode is ColorMode.COLOR_TEMP
    elif observation == "segments":
        assert coord.segment_colors == [(1, 2, 3)] * 15
    else:
        assert coord.color_mode is ParsedMode.MUSIC


def test_static_segment_companion_retains_but_does_not_observe_kelvin(static_coordinator):
    coord = static_coordinator
    coord.color_mode = ParsedMode.COLOUR
    coord.install_static_color(kelvin=4200, source="restored")
    _static_segments(coord, kelvin_to_rgb(4200))
    assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "restored"
    assert coord.rgb_color_source == "segment" and coord._field_revisions["rgb_color"] == 1
    assert "color_temp_kelvin" not in coord._field_revisions
    _static_segments(coord, (1, 2, 3))
    assert coord.color_temp_kelvin is None and "color_temp_kelvin" not in coord._field_revisions
    coord._notify_callback(None, _static_reply(kelvin=5000))
    assert coord.color_temp_kelvin == 5000 and coord.color_temp_kelvin_source == "observed"


@pytest.mark.parametrize("rgb", [True, False])
async def test_static_local_write_keeps_notification_source(static_coordinator, rgb):
    coord = static_coordinator
    coord.is_on = True
    light = GoveeBLELight(coord)
    light.async_write_ha_state = MagicMock()
    frame = _static_reply(rgb=(1, 2, 3)) if rgb else _static_reply(kelvin=4200)

    async def send(packet):
        coord._arm_expected(packet)
        coord._notify_callback(None, frame)

    coord.send_command = AsyncMock(side_effect=send)
    coord.refresh_state = AsyncMock(return_value=True)
    await light.async_turn_on(**({"rgb_color": (1, 2, 3)} if rgb else {"color_temp_kelvin": 4200}))
    field = "rgb_color" if rgb else "color_temp_kelvin"
    assert getattr(coord, f"{field}_source") == "observed"
    assert coord._field_revisions[field] == 1
    assert light.color_mode is (ColorMode.RGB if rgb else ColorMode.COLOR_TEMP)


@pytest.mark.parametrize("restore", ["pre_mode", "recovery"])
async def test_static_command_restoration_is_not_observation(static_coordinator, monkeypatch, restore):
    coord = static_coordinator
    # Direct-colour recovery is separate from observed per-segment restoration.
    coord.profile = replace(coord.profile, segment_count=0, supports_segment_writes=False)
    monkeypatch.setitem(MODEL_PROFILES, coord.model, coord.profile)
    coord.segment_colors = []
    coord.segment_brightness = []
    coord.is_on = True
    coord._notify_callback(None, _static_reply(kelvin=4200))
    prior = coord.capture_effect_control_state()
    coord._pre_mode_snapshot = coord._capture_static_state()
    coord.install_static_color(rgb=(1, 2, 3))
    coord._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    monkeypatch.setattr(coord, "_renew_foreground_lease", lambda: None)
    coord.refresh_state = AsyncMock(return_value=True)
    if restore == "pre_mode":
        await coord.async_restore_pre_mode()
    else:
        assert await coord.async_restore_effect_control_state(prior, overwritten_diy_code=None)
    assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "optimistic"
    assert coord._field_revisions["color_temp_kelvin"] == 1
    if restore == "recovery":
        coord.refresh_state.assert_awaited_once_with(
            expected_on=True, expected_brightness=prior.brightness_pct, expected_color_temp_kelvin=4200
        )
    assert coord._client.write_gatt_char.await_args.args[1] == build_color_temp(4200, coord.model)


async def test_static_verification_uses_actual_colour_query(static_coordinator):
    coord = static_coordinator

    async def write(_uuid, packet, **_kwargs):
        assert packet == generated_protocol_adapter.build_colour_mode_query(coord.model)
        coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=4200))

    coord._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    assert await coord.refresh_state(expected_rgb_color=(1, 2, 3), expected_color_temp_kelvin=4200)
    assert await coord.async_observe_effect({"rgb_color": (1, 2, 3), "color_temp_kelvin": 4200}) is True


@pytest.mark.parametrize("method", ["refresh", "observe"])
@pytest.mark.parametrize("segment_rgb", [(1, 2, 3), (4, 5, 6)])
async def test_direct_rgb_verification_rejects_segment_only_evidence(static_coordinator, method, segment_rgb):
    coord = static_coordinator
    coord.install_static_color(rgb=(1, 2, 3))

    async def write(_uuid, packet, **_kwargs):
        assert packet == generated_protocol_adapter.build_colour_mode_query(coord.model)
        coord._notify_callback(None, _static_reply())
        _static_segments(coord, segment_rgb)

    coord._client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coord._ensure_connected = AsyncMock(return_value=coord._client)
    if method == "refresh":
        assert await coord.refresh_state(expected_rgb_color=(1, 2, 3), timeout=0.01) is False
    else:
        assert await coord.async_observe_effect({"rgb_color": (1, 2, 3)}, timeout=0.01) is None
    assert coord.rgb_color == segment_rgb and coord.rgb_color_source == "segment"
    assert coord._field_revisions["rgb_color"] > 0
    assert coord._field_revisions["segment_colors"] > 0


def test_static_readback_requires_qualified_fields_and_valid_kelvin(static_coordinator):
    coord = static_coordinator
    coord._notify_callback(None, _static_reply(kelvin=0))
    assert coord.color_mode is ParsedMode.COLOUR
    assert "color_temp_kelvin" not in coord._field_revisions
    coord._notify_callback(None, _static_reply(kelvin=1))
    assert coord.packet_log[-1]["reason"] == "semantic_rejected"
    coord.profile = replace(coord.profile, static_readback_echoes_color=False, static_readback_kelvin=False)
    coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=4200))
    assert "rgb_color" not in coord._field_revisions and "color_temp_kelvin" not in coord._field_revisions


async def test_static_failed_write_rollback_keeps_fresh_notification(static_coordinator):
    coord = static_coordinator
    coord.is_on = True
    light = GoveeBLELight(coord)

    async def send(_packet):
        coord._notify_callback(None, _static_reply(rgb=(1, 2, 3)))
        raise RuntimeError("write failed after notification")

    coord.send_command = AsyncMock(side_effect=send)
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(color_temp_kelvin=4200)
    assert coord.rgb_color == (1, 2, 3) and coord.rgb_color_source == "observed"
    assert coord.color_temp_kelvin is None and light.color_mode is ColorMode.RGB


def test_static_segment_write_releases_direct_precedence(static_coordinator):
    coord = static_coordinator
    coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=4200))
    coord.mark_segment_state_optimistic(colours=[(4, 5, 6)] * 15)
    assert coord.rgb_color_source == coord.color_temp_kelvin_source == "retained"
    _static_segments(coord, (4, 5, 6))
    assert coord.rgb_color == (4, 5, 6) and coord.rgb_color_source == "segment"
    assert coord.color_temp_kelvin is None and coord._field_revisions["color_temp_kelvin"] == 1


@pytest.mark.parametrize("kelvin", [None, 4200])
async def test_failed_segment_write_preserves_fresh_static_provenance(static_coordinator, kelvin):
    coord = static_coordinator
    coord.install_static_color(rgb=(9, 8, 7))

    async def send(_packet, *, write_guard):
        write_guard()
        coord._notify_callback(None, _static_reply(rgb=(1, 2, 3), kelvin=kelvin))
        raise RuntimeError("segment write failed after notification")

    coord.send_command = AsyncMock(side_effect=send)
    coord.async_refresh_segments = AsyncMock(return_value=False)
    with pytest.raises(RuntimeError, match="segment write failed"):
        await coord.async_paint_segments([([1], (4, 5, 6))])
    assert coord.rgb_color_source == "observed"
    if kelvin is not None:
        assert coord.color_temp_kelvin_source == "observed"
    _static_segments(coord, (4, 5, 6))
    assert coord.rgb_color == (1, 2, 3) and coord.color_temp_kelvin == kelvin
    assert coord.rgb_color_source == "observed"


@pytest.mark.parametrize("extra", [False, True])
@pytest.mark.parametrize("change", ["companion", "mode_roundtrip"])
async def test_static_restore_rechecks_companion_and_mode_revision(static_coordinator, extra, change):
    coord = static_coordinator
    coord.color_mode = ParsedMode.COLOUR
    light = GoveeBLELight(coord)
    stored = {"color_mode": ColorMode.COLOR_TEMP, "color_temp_kelvin": 4200}

    def notify():
        if change == "companion":
            _static_segments(coord, kelvin_to_rgb(4200))
        else:
            coord.color_mode = ParsedMode.MUSIC
            coord._mark_received(ReadDomain.COLOUR_MODE, "color_mode")
            coord._notify_callback(None, _static_reply())

    async def state():
        if not extra:
            notify()
        return SimpleNamespace(attributes={} if extra else stored)

    async def extra_data():
        notify()
        return RestoredExtraData(stored)

    light.async_get_last_state = AsyncMock(side_effect=state)
    light.async_get_last_extra_data = AsyncMock(side_effect=extra_data)
    await light._async_restore_static_color()
    if change == "companion":
        assert coord.color_temp_kelvin == 4200 and coord.color_temp_kelvin_source == "restored"
        assert light.color_mode is ColorMode.COLOR_TEMP
    else:
        assert coord.color_temp_kelvin is None
    assert "color_temp_kelvin" not in coord._field_revisions


@pytest.mark.parametrize("model", ["H617A", "H6199", "H6076"])
async def test_static_direct_verification_is_not_enabled_for_existing_models(hass, model):
    coord = GoveeBLECoordinator(hass, "AA:BB:CC:DD:EE:FF", model, configuration_url=None)
    coord._ensure_connected = AsyncMock()
    assert not await coord.refresh_state(expected_rgb_color=(1, 2, 3))
    assert not await coord.refresh_state(expected_color_temp_kelvin=4200)
    assert await coord.async_observe_effect({"rgb_color": (1, 2, 3)}) is None
    assert await coord.async_observe_effect({"color_temp_kelvin": 4200}) is None
    coord._ensure_connected.assert_not_called()


REPRESENTATIVE_ROOTS = (
    pytest.param(CommandWrite, COMMAND_STATIC, id="H617A command"),
    pytest.param(StatusReply, STATUS_SEGMENTS, id="H617A status"),
    pytest.param(StatusQuery, H617A_SEGMENT_QUERY, id="H617A segment query"),
    pytest.param(H6199StatusQuery, H6199_SEGMENT_QUERY, id="H6199 segment query"),
    pytest.param(H6199CommandAck, H6199_DISPLAY_ACK, id="H6199 command acknowledgement"),
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


@pytest.mark.parametrize(
    ("frame", "opcode"),
    [
        (H6199_POWER_ACK, "power"),
        (H6199_MODE_ACK, "mode"),
        (H6199_DISPLAY_ACK, "display_setting"),
        (H6199_RELATIVE_BRIGHTNESS_ACK, "relative_brightness"),
    ],
)
def test_h6199_generic_command_acknowledgements_are_distinct_from_writes(frame: bytes, opcode: str) -> None:
    parsed = _parse(H6199CommandAck, frame)

    assert parsed.opcode.name == opcode
    assert parsed.status == 0
    assert generated_protocol_adapter.parse_command_ack_result(frame, "H6199").parsed is not None
    if opcode in {"display_setting", "relative_brightness"}:
        assert generated_protocol_adapter.parse_command_result(frame, "H6199").parsed is None


def test_h6199_command_acknowledgement_rejects_unobserved_opcodes() -> None:
    frame = bytearray(H6199_DISPLAY_ACK)
    frame[1] = 0x99
    frame[-1] = xor_checksum(frame[:-1])

    assert generated_protocol_adapter.parse_command_ack_result(bytes(frame), "H6199").parsed is None


@pytest.mark.parametrize("grammar", [None, "unknown"])
@pytest.mark.parametrize("direction", ["command", "status"])
def test_missing_or_unknown_grammar_fails_closed_only_in_its_direction(monkeypatch, grammar, direction) -> None:
    monkeypatch.setitem(
        MODEL_PROFILES,
        "H617A",
        replace(
            MODEL_PROFILES["H617A"],
            read_domains=frozenset(),
            setup_required_read_domains=frozenset(),
            **{f"{direction}_grammar": grammar},
        ),
    )
    command = generated_protocol_adapter.parse_command_result(COMMAND_STATIC)
    status = generated_protocol_adapter.parse_status_result(STATUS_SEGMENTS)
    rejected, accepted = (command, status) if direction == "command" else (status, command)
    assert rejected.parsed is None and rejected.parser is None
    assert rejected.rejection is ProtocolParseRejection.UNSUPPORTED_MODEL
    assert accepted.parsed is not None and accepted.rejection is None

    if direction == "command":
        assert expectations_from_packet(COMMAND_STATIC) == {}
        for build, args in (
            (generated_protocol_adapter.build_power, (True,)),
            (generated_protocol_adapter.build_brightness_query, ()),
            (generated_protocol_adapter.build_segment_query, (1,)),
            (generated_protocol_adapter.build_segment_colour, (1, 10, 20, 30)),
        ):
            with pytest.raises(ValueError, match="grammar"):
                build(*args)
    else:
        assert generated_protocol_adapter.build_power(True) == bytes.fromhex("3301010000000000000000000000000000000033")
        assert generated_protocol_adapter.build_segment_query(5) == H617A_SEGMENT_QUERY


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
    h6199_query = _parse(H6199StatusQuery, H6199_SEGMENT_QUERY)
    assert (h617a_query.domain.name, h617a_query.body.group) == ("segments", 5)
    assert (h6199_query.domain.name, h6199_query.body.group) == ("segments", 4)


@pytest.mark.parametrize("group", [1, 2, 3, 4])
def test_h6199_segment_pages_preserve_opaque_tail(group: int) -> None:
    records = bytes.fromhex("00000000 64010203 32112233 27abcdef")
    frame = bytes((0xAA, 0xA5, group)) + records
    frame += bytes((xor_checksum(frame),))
    parsed = _parse(H6199StatusReply, frame)
    expected_count = 3 if group == 4 else 4
    assert parsed.body.num_segments == len(parsed.body.segments) == expected_count
    assert parsed.body.segments[0].brightness == 0
    assert parsed.body.unused == (list(records[-4:]) if group == 4 else [])
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(20)))
    parsed._write(output)
    assert output.to_byte_array() == frame


@pytest.mark.skipif(not _GENERATED_DIR, reason="Synthetic layouts are all-schema fixtures, not runtime roots")
@pytest.mark.parametrize(
    ("schema", "class_name", "read_domains"),
    [
        ("h66a0_status_reply", "H66a0StatusReply", frozenset({ReadDomain.SEGMENTS})),
        (
            "synthetic_mixed_status_reply",
            "SyntheticMixedStatusReply",
            frozenset({ReadDomain.POWER, ReadDomain.SEGMENTS}),
        ),
    ],
)
async def test_four_slot_profile_observes_every_declared_domain(hass, monkeypatch, schema, class_name, read_domains):
    root = _generated(schema, class_name)
    first = bytes.fromhex("aaa50164e5444464ffae5464ffae5464cf2e2e24")
    final = bytes.fromhex("aaa50464dc3b3b64e54444000000000000000032")
    # Pages 2/3 are synthetic, including a meaningful black/off segment.
    second = bytes.fromhex("aaa502 00000000 01010203 02040506 03070809")
    second += bytes((xor_checksum(second),))
    third = bytes.fromhex("aaa503 040a0b0c 050d0e0f 06101112 07131415")
    third += bytes((xor_checksum(third),))
    for frame, count in ((first, 4), (second, 4), (third, 4), (final, 2)):
        parsed = _parse(root, frame)
        assert parsed.body.num_segments == len(parsed.body.segments) == count
        assert len(parsed.body.segments) * 4 + len(parsed.body.unused) == 16
        parsed._fetch_instances()
        parsed._check()
        output = KaitaiStream(io.BytesIO(bytes(20)))
        parsed._write(output)
        assert output.to_byte_array() == frame

    # Unused slots are opaque, not a zero constraint or extra semantic records.
    nonzero_final = final[:11] + bytes.fromhex("deadbeef 12345678")
    nonzero_final += bytes((xor_checksum(nonzero_final),))
    parsed = _parse(root, nonzero_final)
    assert parsed.body.unused == list(bytes.fromhex("deadbeef12345678"))
    parsed._fetch_instances()
    parsed._check()
    output = KaitaiStream(io.BytesIO(bytes(20)))
    parsed._write(output)
    assert output.to_byte_array() == nonzero_final

    # A synthetic exact model reuses outbound H617A bytes and independently selects
    # the speculative layout. Neither the real H66A0 nor H617A changes support.
    model = "H7000"
    status_grammar = "test-four-slot-pages"
    profile = ModelProfile(
        "Synthetic 14-segment device",
        command_grammar="H617A",
        status_grammar=status_grammar,
        read_domains=read_domains,
        segment_count=14,
        segment_group_size=4,
        supports_segment_writes=True,
        whole_device_mask=0x3FFF,
    )
    monkeypatch.setitem(MODEL_PROFILES, model, profile)
    monkeypatch.setitem(generated_protocol_adapter._STATUS_ROOTS, status_grammar, (schema, root))
    coordinator = GoveeBLECoordinator(
        hass, "AA:BB:CC:DD:EE:FF", model, configuration_url="homeassistant://ha-govee-led-ble/editor/test"
    )
    assert coordinator.profile is profile
    command = generated_protocol_adapter.build_power(True, model)
    assert command == bytes.fromhex("3301010000000000000000000000000000000033")
    parsed_command = generated_protocol_adapter.parse_command_result(command, model)
    assert parsed_command.parser == "command_write" and parsed_command.parsed is not None
    assert parsed_command.parsed.body.is_on == 1
    assert generated_protocol_adapter.parse_status_result(first, model).parser == schema
    assert generated_protocol_adapter.parse_status_result(STATUS_SEGMENTS, "H617A").parsed is not None
    assert (
        generated_protocol_adapter.parse_status_result(first, "H617A").rejection
        is ProtocolParseRejection.SCHEMA_REJECTED
    )
    assert get_profile("H66A0") is UNSUPPORTED_PROFILE
    assert (
        generated_protocol_adapter.parse_status_result(first, "H66A0").rejection
        is ProtocolParseRejection.UNSUPPORTED_MODEL
    )
    assert (
        generated_protocol_adapter.parse_command_result(command, "H66A0").rejection
        is ProtocolParseRejection.UNSUPPORTED_MODEL
    )

    for frame in (final, first, first, third):
        coordinator._notify_callback(None, bytearray(frame))
        assert coordinator.segment_state_source == "initial"
        assert coordinator._field_revisions.get("segment_colors", 0) == 0

    coordinator._notify_callback(None, bytearray(second))
    assert coordinator.segment_state_source == "observed"
    assert coordinator.segment_state_observed_at is not None
    assert coordinator._field_revisions["segment_colors"] == 1
    assert coordinator.segment_brightness == [100] * 4 + list(range(8)) + [100, 100]
    assert coordinator.segment_colors == [
        (229, 68, 68),
        (255, 174, 84),
        (255, 174, 84),
        (207, 46, 46),
        (0, 0, 0),
        (1, 2, 3),
        (4, 5, 6),
        (7, 8, 9),
        (10, 11, 12),
        (13, 14, 15),
        (16, 17, 18),
        (19, 20, 21),
        (220, 59, 59),
        (229, 68, 68),
    ]
    for frame in (nonzero_final, first, second, third):
        coordinator._notify_callback(None, bytearray(frame))
    assert coordinator._field_revisions["segment_colors"] == 2
    assert len(coordinator.segment_colors) == len(coordinator.segment_brightness) == 14
    assert coordinator.segment_colors[-2:] == [(220, 59, 59), (229, 68, 68)]

    # Exercise real command/query/notification paths, mocking only the BLE connection.
    power_reply = bytes.fromhex("aa010100000000000000000000000000000000aa")
    replies = {}
    if profile.can_read(ReadDomain.POWER):
        replies[generated_protocol_adapter.build_power_query("H617A")] = power_reply
    replies.update(
        (generated_protocol_adapter.build_segment_query(group, "H617A"), frame)
        for group, frame in enumerate((first, second, third, final), 1)
    )

    async def write(_uuid, packet, **_kwargs):
        if packet != command:
            coordinator._notify_callback(None, bytearray(replies[packet]))

    client = MagicMock(is_connected=True, write_gatt_char=AsyncMock(side_effect=write))
    coordinator._client = client
    monkeypatch.setattr(coordinator, "_ensure_connected", AsyncMock(return_value=client))
    monkeypatch.setattr(coordinator, "_reset_disconnect_timer", lambda: None)
    await coordinator.send_command(command)
    client.write_gatt_char.assert_awaited_once_with(WRITE_UUID, command, response=False)
    client.write_gatt_char.reset_mock()
    if profile.can_read(ReadDomain.POWER):
        assert generated_protocol_adapter.parse_status_result(power_reply, "H617A").parsed is not None
        assert await coordinator.refresh_state(expected_on=True, timeout=0.05)
        assert coordinator.is_on
    assert await coordinator.async_refresh_segments(timeout=0.05)
    assert coordinator._field_revisions["segment_colors"] == 3
    assert set(coordinator._domain_revisions) == profile.read_domains
    assert client.write_gatt_char.await_args_list == [call(WRITE_UUID, query, response=False) for query in replies]


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
    assert (body.tail.no_rhythm_speed, body.tail.rhythm_speed, body.tail_len, len(body.padding)) == (10, 20, 2, 6)

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
