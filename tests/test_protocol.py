"""Unit tests for the Govee BLE protocol module."""

import base64

import pytest

from custom_components.govee_ble_lights.protocol import (
    ColorMode,
    PacketHeader,
    PacketType,
    build_brightness,
    build_brightness_query,
    build_color_mode_query,
    build_color_rgb,
    build_color_temp,
    build_keep_alive,
    build_music_mode_with_color,
    build_packet,
    build_power,
    build_scene,
    build_scene_multi,
    build_state_query,
    build_video_mode,
    kelvin_to_rgb,
    parse_brightness_response,
    parse_color_mode_response,
    parse_power_response,
    xor_checksum,
)

# --- XOR checksum ---


@pytest.mark.parametrize(
    "data,expected",
    [
        (bytes(19), 0x00),
        (bytearray([0x33, 0x01, 0x01] + [0x00] * 16), 0x33),
        (bytearray([0x33, 0x01, 0x00] + [0x00] * 16), 0x32),
        (bytearray([0xAA, 0x01] + [0x00] * 17), 0xAB),
    ],
)
def test_xor_checksum(data, expected):
    assert xor_checksum(data) == expected


# --- Packet basics ---


def test_packet_length_and_checksum():
    pkt = build_packet(0x33, 0x01, [0x01])
    assert len(pkt) == 20
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_packet_padding():
    pkt = build_packet(0x33, 0x01, [])
    assert all(pkt[i] == 0x00 for i in range(2, 19))


def test_packet_truncates_long_params():
    assert len(build_packet(0x33, 0x01, list(range(20)))) == 20


# --- Power ---


@pytest.mark.parametrize(
    "on,hex_str",
    [
        (True, "3301010000000000000000000000000000000033"),
        (False, "3301000000000000000000000000000000000032"),
    ],
)
def test_power(on, hex_str):
    pkt = build_power(on)
    assert pkt == bytes.fromhex(hex_str)
    assert len(pkt) == 20


# --- Brightness ---


@pytest.mark.parametrize("val,expected_byte", [(100, 100), (0, 0), (200, 100), (-10, 0)])
def test_brightness(val, expected_byte):
    pkt = build_brightness(val)
    assert pkt[0:2] == bytes([0x33, 0x04])
    assert pkt[2] == expected_byte
    assert len(pkt) == 20
    assert xor_checksum(pkt[:19]) == pkt[19]


# --- Color RGB ---


def test_color_rgb():
    pkt = build_color_rgb(255, 0, 0)
    assert pkt[:14] == bytes([0x33, 0x05, 0x15, 0x01, 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x7F])
    assert len(pkt) == 20


def test_color_rgb_clamp():
    pkt = build_color_rgb(300, -10, 128)
    assert (pkt[4], pkt[5], pkt[6]) == (255, 0, 128)


# --- Color temperature ---


def test_color_temp():
    pkt = build_color_temp(4000)
    assert len(pkt) == 20
    assert pkt[2] == 0x15  # segmented mode


@pytest.mark.parametrize(
    "kelvin,check",
    [
        (1000, lambda r, g, b: r == 255 and g > 0),
        (2700, lambda r, g, b: r == 255 and g > 100 and b < g),
        (5500, lambda r, g, b: r == 255 and g > 200 and b > 200),
        (6500, lambda r, g, b: r == 255 and b > 200),
        (10000, lambda r, g, b: b > 200),
        (500, lambda r, g, b: 0 <= r <= 255),  # clamp low
        (20000, lambda r, g, b: 0 <= r <= 255),  # clamp high
    ],
)
def test_kelvin_to_rgb(kelvin, check):
    r, g, b = kelvin_to_rgb(kelvin)
    assert check(r, g, b), f"Failed at {kelvin}K: ({r},{g},{b})"


def test_kelvin_output_range():
    for k in range(1000, 10001, 500):
        r, g, b = kelvin_to_rgb(k)
        assert all(0 <= c <= 255 for c in (r, g, b)), f"Out of range at {k}K"


# --- Scenes ---


@pytest.mark.parametrize(
    "code,hex_str",
    [
        (0x00, "3305040000000000000000000000000000000032"),
        (0x01, "3305040100000000000000000000000000000033"),
        (0x04, "3305040400000000000000000000000000000036"),
        (0x16, "3305041600000000000000000000000000000024"),
        (0x08, "330504080000000000000000000000000000003a"),
        (0x0A, "3305040a00000000000000000000000000000038"),
        (0x10, "3305041000000000000000000000000000000022"),
    ],
)
def test_scene_simple(code, hex_str):
    assert build_scene(code) == bytes.fromhex(hex_str)


def test_scene_multi_byte_code():
    pkt = build_scene(2163)
    assert (pkt[2], pkt[3], pkt[4]) == (0x04, 0x73, 0x08)
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_scene_multi_empty_param():
    pkts = build_scene_multi("", 22)
    assert pkts == [build_scene(22)]


def test_scene_multi_structure():
    raw = bytes(20)
    pkts = build_scene_multi(base64.b64encode(raw).decode(), 100)
    assert len(pkts) > 1
    for pkt in pkts:
        assert len(pkt) == 20
        assert xor_checksum(pkt[:19]) == pkt[19]
    assert pkts[0][0:2] == bytes([0xA3, 0x00])
    assert pkts[-2][0:2] == bytes([0xA3, 0xFF])
    assert pkts[-1][0:3] == bytes([0x33, 0x05, 0x04])


def test_scene_multi_real_forest():
    forest_param = (
        "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8F"
        "AgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC"
        "7hQBAP8AAAAAAAAAAA=="
    )
    pkts = build_scene_multi(forest_param, 2163)
    assert len(pkts) > 2
    for pkt in pkts:
        assert len(pkt) == 20
        assert xor_checksum(pkt[:19]) == pkt[19]
    assert (pkts[0][0], pkts[0][2]) == (0xA3, 0x01)
    assert (pkts[-1][3], pkts[-1][4]) == (0x73, 0x08)


# --- Status queries ---


@pytest.mark.parametrize(
    "builder,hex_str",
    [
        (build_state_query, "AA010000000000000000000000000000000000AB"),
        (build_brightness_query, "AA040000000000000000000000000000000000AE"),
        (build_color_mode_query, "AA050000000000000000000000000000000000AF"),
    ],
)
def test_status_queries(builder, hex_str):
    assert builder() == bytes.fromhex(hex_str)


def test_keep_alive_is_state_query():
    assert build_keep_alive() == build_state_query()


# --- Video mode ---


def test_video_mode_default():
    pkt = build_video_mode()
    assert (pkt[0], pkt[1], pkt[2], pkt[3], pkt[4], pkt[5]) == (0x33, 0x05, 0x00, 0x01, 0x00, 100)
    assert len(pkt) == 20
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_video_mode_game():
    pkt = build_video_mode(full_screen=False, game_mode=True, saturation=75)
    assert (pkt[3], pkt[4], pkt[5]) == (0x00, 0x01, 75)


@pytest.mark.parametrize("sat,expected", [(200, 100), (-5, 0)])
def test_video_mode_saturation_clamp(sat, expected):
    assert build_video_mode(saturation=sat)[5] == expected


def test_video_mode_sound_effects():
    pkt = build_video_mode(sound_effects=True, sound_effects_softness=50)
    assert (pkt[6], pkt[7]) == (0x01, 50)
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_video_mode_sound_effects_off():
    assert build_video_mode(sound_effects=False)[6] == 0x00


@pytest.mark.parametrize("soft,expected", [(200, 100), (-5, 0)])
def test_video_mode_softness_clamp(soft, expected):
    assert build_video_mode(sound_effects=True, sound_effects_softness=soft)[7] == expected


def test_video_mode_all_params():
    pkt = build_video_mode(
        full_screen=False, game_mode=True, saturation=60, sound_effects=True, sound_effects_softness=75
    )
    assert pkt[2:8] == bytes([0x00, 0x00, 0x01, 60, 0x01, 75])
    assert xor_checksum(pkt[:19]) == pkt[19]


# --- Music mode ---


def test_music_mode_basic():
    pkt = build_music_mode_with_color(0x05, sensitivity=80)
    assert pkt[0:6] == bytes([0x33, 0x05, 0x13, 0x05, 80, 0x00])
    assert len(pkt) == 20
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_music_mode_with_color():
    pkt = build_music_mode_with_color(0x04, sensitivity=100, color=(255, 0, 128))
    assert (pkt[6], pkt[7], pkt[8], pkt[9]) == (0x01, 255, 0, 128)


def test_music_mode_sensitivity_clamp():
    assert build_music_mode_with_color(0x03, sensitivity=150)[4] == 100


def test_music_mode_calm():
    pkt = build_music_mode_with_color(0x03, sensitivity=80, calm=True)
    assert pkt[5] == 0x01
    assert xor_checksum(pkt[:19]) == pkt[19]


def test_music_mode_calm_with_color():
    pkt = build_music_mode_with_color(0x03, sensitivity=50, calm=True, color=(128, 64, 32))
    assert (pkt[5], pkt[6], pkt[7], pkt[8], pkt[9]) == (0x01, 0x01, 128, 64, 32)


# --- Parse responses ---


def test_parse_power():
    assert parse_power_response(bytes([0x01, 0x00])) is True
    assert parse_power_response(bytes([0x00, 0x00])) is False


def test_parse_brightness():
    assert parse_brightness_response(bytes([75, 0x00])) == 75


def test_parse_color_mode_video():
    p = parse_color_mode_response(bytes([0x00, 0x00, 0x01, 42, 0x01, 55]))
    assert p.effect == "video: game"
    assert p.video_full_screen is False
    assert p.video_saturation == 42
    assert p.video_sound_effects is True
    assert p.video_sound_effects_softness == 55


def test_parse_color_mode_music():
    p = parse_color_mode_response(bytes([0x13, 0x04, 77, 0x00, 0x01, 1, 2, 3]))
    assert p.effect == "music: spectrum"
    assert p.music_sensitivity == 77
    assert p.music_color == (1, 2, 3)


def test_parse_color_mode_static():
    p = parse_color_mode_response(bytes([0x15, 0x01, 10, 20, 30]))
    assert p.rgb_color == (10, 20, 30)
    p2 = parse_color_mode_response(bytes([0x15, 0x02, 0x80]))
    assert p2.white_brightness == 50


def test_parse_color_mode_empty_raises():
    with pytest.raises(ValueError):
        parse_color_mode_response(bytes())


# --- Enum values ---


def test_enum_values():
    assert (PacketHeader.COMMAND, PacketHeader.STATUS) == (0x33, 0xAA)
    assert (PacketType.POWER, PacketType.BRIGHTNESS, PacketType.COLOR) == (0x01, 0x04, 0x05)
    assert (ColorMode.VIDEO, ColorMode.MUSIC, ColorMode.STATIC) == (0x00, 0x13, 0x15)
