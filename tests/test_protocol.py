"""Unit tests for the Govee BLE protocol module."""

import base64

import pytest

from custom_components.ha_govee_led_ble import protocol as proto

H = bytes.fromhex


def _valid(pkt):
    assert len(pkt) == 20 and proto.xor_checksum(pkt[:19]) == pkt[19]


def test_xor_checksum():
    assert proto.xor_checksum(bytes(19)) == 0x00
    assert proto.xor_checksum(bytearray([0x33, 0x01, 0x01] + [0x00] * 16)) == 0x33
    assert proto.xor_checksum(bytearray([0x33, 0x01, 0x00] + [0x00] * 16)) == 0x32
    assert proto.xor_checksum(bytearray([0xAA, 0x01] + [0x00] * 17)) == 0xAB


def test_packet_basics():
    _valid(proto.build_packet(0x33, 0x01, [0x01]))
    pkt = proto.build_packet(0x33, 0x01, [])
    assert all(pkt[i] == 0x00 for i in range(2, 19))
    assert len(proto.build_packet(0x33, 0x01, list(range(20)))) == 20


@pytest.mark.parametrize(
    "on,h", [(True, "3301010000000000000000000000000000000033"), (False, "3301000000000000000000000000000000000032")]
)
def test_power(on, h):
    pkt = proto.build_power(on)
    assert pkt == H(h) and len(pkt) == 20


@pytest.mark.parametrize("val,exp", [(100, 100), (0, 0), (200, 100), (-10, 0)])
def test_brightness(val, exp):
    pkt = proto.build_brightness(val)
    assert pkt[0:2] == bytes([0x33, 0x04]) and pkt[2] == exp
    _valid(pkt)


@pytest.mark.parametrize("val,raw", [(0, 0), (50, 128), (100, 255), (120, 255), (-1, 0)])
def test_white_brightness(val, raw):
    pkt = proto.build_white_brightness(val)
    assert pkt[0:5] == bytes([0x33, 0x05, 0x15, 0x02, raw])
    _valid(pkt)


def test_color():
    pkt = proto.build_color_rgb(255, 0, 0)
    assert pkt[:14] == bytes([0x33, 0x05, 0x15, 0x01, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0xFF, 0x7F])
    assert len(pkt) == 20
    assert tuple(proto.build_color_rgb(300, -10, 128)[4:7]) == (255, 0, 128)
    pkt = proto.build_color_temp(4000)
    assert len(pkt) == 20 and pkt[2] == 0x15


@pytest.mark.parametrize(
    "kelvin,check",
    [
        (1000, lambda r, g, b: r == 255 and g > 0),
        (2700, lambda r, g, b: r == 255 and g > 100 and b < g),
        (5500, lambda r, g, b: r == 255 and g > 200 and b > 200),
        (6500, lambda r, g, b: r == 255 and b > 200),
        (10000, lambda r, g, b: b > 200),
        (500, lambda r, g, b: 0 <= r <= 255),
        (20000, lambda r, g, b: 0 <= r <= 255),
    ],
)
def test_kelvin_to_rgb(kelvin, check):
    r, g, b = proto.kelvin_to_rgb(kelvin)
    assert check(r, g, b), f"Failed at {kelvin}K: ({r},{g},{b})"


def test_kelvin_output_range():
    for k in range(1000, 10001, 500):
        assert all(0 <= c <= 255 for c in proto.kelvin_to_rgb(k)), f"Out of range at {k}K"


def test_scene():
    assert proto.build_scene(0x00) == H("3305040000000000000000000000000000000032")
    assert proto.build_scene(0x01) == H("3305040100000000000000000000000000000033")
    assert proto.build_scene(0x04) == H("3305040400000000000000000000000000000036")
    assert proto.build_scene(0x16) == H("3305041600000000000000000000000000000024")
    assert proto.build_scene(0x08) == H("330504080000000000000000000000000000003a")
    assert proto.build_scene(0x0A) == H("3305040a00000000000000000000000000000038")
    assert proto.build_scene(0x10) == H("3305041000000000000000000000000000000022")


def test_scene_multi():
    pkt = proto.build_scene(2163)
    assert (pkt[2], pkt[3], pkt[4]) == (0x04, 0x73, 0x08)
    _valid(pkt)
    assert proto.build_scene_multi("", 22) == [proto.build_scene(22)]
    pkts = proto.build_scene_multi(base64.b64encode(bytes(20)).decode(), 100)
    assert len(pkts) > 1
    for p in pkts:
        _valid(p)
    assert pkts[0][0:2] == bytes([0xA3, 0x00])
    assert pkts[-2][0:2] == bytes([0xA3, 0xFF])
    assert pkts[-1][0:3] == bytes([0x33, 0x05, 0x04])
    forest = (
        "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8F"
        "AgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC"
        "7hQBAP8AAAAAAAAAAA=="
    )
    pkts = proto.build_scene_multi(forest, 2163)
    assert len(pkts) > 2
    for p in pkts:
        _valid(p)
    assert (pkts[0][0], pkts[0][2]) == (0xA3, 0x01)
    assert (pkts[-1][3], pkts[-1][4]) == (0x73, 0x08)


def test_constants():
    assert proto.STATE_QUERY == H("AA010000000000000000000000000000000000AB")
    assert proto.BRIGHTNESS_QUERY == H("AA040000000000000000000000000000000000AE")
    assert proto.COLOR_MODE_QUERY == H("AA050000000000000000000000000000000000AF")
    assert proto.KEEP_ALIVE == proto.STATE_QUERY
    assert (proto.COMMAND_HEADER, proto.STATUS_HEADER) == (0x33, 0xAA)
    assert (proto.POWER_PACKET_TYPE, proto.BRIGHTNESS_PACKET_TYPE, proto.COLOR_PACKET_TYPE) == (0x01, 0x04, 0x05)
    assert (proto.COLOR_MODE_VIDEO, proto.COLOR_MODE_MUSIC, proto.COLOR_MODE_STATIC) == (0x00, 0x13, 0x15)


def test_video_mode():
    def chk(kw, idx, exp):
        pkt = proto.build_video_mode(**kw)
        assert (tuple(pkt[idx]) if isinstance(idx, slice) else pkt[idx]) == exp
        _valid(pkt)

    chk({}, slice(0, 6), (0x33, 0x05, 0x00, 0x01, 0x00, 100))
    chk(dict(full_screen=False, game_mode=True, saturation=75), slice(3, 6), (0x00, 0x01, 75))
    chk(dict(sound_effects=True, sound_effects_softness=50), slice(6, 8), (0x01, 50))
    chk(dict(sound_effects=False), 6, 0x00)
    chk(dict(saturation=200), 5, 100)
    chk(dict(saturation=-5), 5, 0)
    chk(dict(sound_effects=True, sound_effects_softness=200), 7, 100)
    chk(dict(sound_effects=True, sound_effects_softness=-5), 7, 0)
    chk(
        dict(full_screen=False, game_mode=True, saturation=60, sound_effects=True, sound_effects_softness=75),
        slice(2, 8),
        (0x00, 0x00, 0x01, 60, 0x01, 75),
    )


def test_music_mode():
    def chk(mode, kw, idx, exp):
        pkt = proto.build_music_mode_with_color(mode, **kw)
        assert (tuple(pkt[idx]) if isinstance(idx, slice) else pkt[idx]) == exp
        _valid(pkt)

    chk(0x05, dict(sensitivity=80), slice(0, 6), (0x33, 0x05, 0x13, 0x05, 80, 0x00))
    chk(0x04, dict(sensitivity=100, color=(255, 0, 128)), slice(6, 10), (0x01, 255, 0, 128))
    chk(0x03, dict(sensitivity=150), 4, 100)
    chk(0x03, dict(sensitivity=80, calm=True), 5, 0x01)
    chk(0x03, dict(sensitivity=50, calm=True, color=(128, 64, 32)), slice(5, 10), (0x01, 0x01, 128, 64, 32))


def test_parse():
    p = proto.parse_color_mode_response(bytes([0x00, 0x00, 0x01, 42, 0x01, 55]))
    assert p.effect == "video: game" and not p.video_full_screen
    assert (p.video_saturation, p.video_sound_effects, p.video_sound_effects_softness) == (42, True, 55)
    p = proto.parse_color_mode_response(bytes([0x13, 0x04, 77, 0x00, 0x01, 1, 2, 3]))
    assert p.effect == "music: spectrum" and p.music_sensitivity == 77 and p.music_calm is False and p.music_color == (1, 2, 3)
    p = proto.parse_color_mode_response(bytes([0x13, 0x03, 88, 0x01, 0x00]))
    assert p.effect == "music: rhythm" and p.music_sensitivity == 88 and p.music_calm is True
    assert proto.parse_color_mode_response(bytes([0x15, 0x01, 10, 20, 30])).rgb_color == (10, 20, 30)
    assert proto.parse_color_mode_response(bytes([0x15, 0x02, 0x80])).white_brightness == 50
    with pytest.raises(ValueError):
        proto.parse_color_mode_response(b"")
