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
    build_gradient,
    build_keep_alive,
    build_music_mode_with_color,
    build_packet,
    build_power,
    build_scene,
    build_scene_multi,
    build_state_query,
    build_video_mode,
    build_white_brightness,
    kelvin_to_rgb,
    parse_brightness_response,
    parse_color_mode_response,
    parse_power_response,
    xor_checksum,
)


def test_xor_all_zeros():
    assert xor_checksum(bytes(19)) == 0x00


def test_xor_power_on():
    data = bytearray([0x33, 0x01, 0x01] + [0x00] * 16)
    assert xor_checksum(data) == 0x33


def test_xor_power_off():
    data = bytearray([0x33, 0x01, 0x00] + [0x00] * 16)
    assert xor_checksum(data) == 0x32


def test_xor_state_query():
    data = bytearray([0xAA, 0x01] + [0x00] * 17)
    assert xor_checksum(data) == 0xAB


def test_packet_length():
    assert len(build_packet(0x33, 0x01, [0x01])) == 20


def test_packet_checksum_valid():
    packet = build_packet(0x33, 0x01, [0x01])
    assert xor_checksum(packet[:19]) == packet[19]


def test_packet_padding():
    packet = build_packet(0x33, 0x01, [])
    for i in range(2, 19):
        assert packet[i] == 0x00


def test_packet_truncates_long_params():
    params = list(range(20))
    packet = build_packet(0x33, 0x01, params)
    assert len(packet) == 20


def test_power_on():
    expected = bytes.fromhex("3301010000000000000000000000000000000033")
    assert build_power(True) == expected


def test_power_off():
    expected = bytes.fromhex("3301000000000000000000000000000000000032")
    assert build_power(False) == expected


def test_power_length():
    assert len(build_power(True)) == 20
    assert len(build_power(False)) == 20


def test_brightness_100():
    packet = build_brightness(100)
    assert len(packet) == 20
    assert packet[0] == 0x33
    assert packet[1] == 0x04
    assert packet[2] == 100


def test_brightness_0():
    assert build_brightness(0)[2] == 0


def test_brightness_clamp_high():
    assert build_brightness(200)[2] == 100


def test_brightness_clamp_low():
    assert build_brightness(-10)[2] == 0


def test_brightness_checksum():
    packet = build_brightness(50)
    assert xor_checksum(packet[:19]) == packet[19]


def test_white_brightness_100():
    packet = build_white_brightness(100)
    assert packet[0] == 0x33
    assert packet[1] == 0x05
    assert packet[2] == 0x15  # static/segment mode
    assert packet[3] == 0x02  # white brightness sub-command
    assert packet[4] == 0xFF  # 100% -> 255
    assert packet[12] == 0xFF  # seg_lo (all)
    assert packet[13] == 0x7F  # seg_hi (15 segments)
    assert xor_checksum(packet[:19]) == packet[19]


def test_white_brightness_clamp_high():
    assert build_white_brightness(200)[4] == 0xFF


def test_white_brightness_clamp_low():
    assert build_white_brightness(-10)[4] == 0x00


def test_color_red_segmented():
    packet = build_color_rgb(255, 0, 0)
    assert len(packet) == 20
    assert packet[0] == 0x33
    assert packet[1] == 0x05
    assert packet[2] == 0x15  # segmented mode
    assert packet[3] == 0x01  # set color sub-command
    assert packet[4] == 0xFF  # R
    assert packet[5] == 0x00  # G
    assert packet[6] == 0x00  # B
    assert packet[12] == 0xFF  # seg_lo (all)
    assert packet[13] == 0x7F  # seg_hi (15 segments)


def test_color_matches_known_format():
    packet = build_color_rgb(0xFF, 0x00, 0x00)
    assert packet[:14] == bytes(
        [
            0x33,
            0x05,
            0x15,
            0x01,
            0xFF,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0xFF,
            0x7F,
        ]
    )


def test_color_clamp():
    packet = build_color_rgb(300, -10, 128)
    assert packet[4] == 255
    assert packet[5] == 0
    assert packet[6] == 128


def test_packet_length_color_temp():
    assert len(build_color_temp(4000)) == 20


def test_uses_segmented_mode():
    packet = build_color_temp(4000)
    assert packet[2] == 0x15


def test_warm_has_high_red():
    r, g, b = kelvin_to_rgb(2700)
    assert r == 255
    assert g > 100
    assert b < g


def test_cool_has_high_blue():
    r, g, b = kelvin_to_rgb(6500)
    assert r == 255
    assert b > 200


def test_scene_sunrise():
    expected = bytes.fromhex("3305040000000000000000000000000000000032")
    assert build_scene(0x00) == expected


def test_scene_sunset():
    expected = bytes.fromhex("3305040100000000000000000000000000000033")
    assert build_scene(0x01) == expected


def test_scene_movie():
    expected = bytes.fromhex("3305040400000000000000000000000000000036")
    assert build_scene(0x04) == expected


def test_scene_rainbow():
    expected = bytes.fromhex("3305041600000000000000000000000000000024")
    assert build_scene(0x16) == expected


def test_scene_twinkle():
    """Twinkle (was 'blinking' — renamed per Govee API)."""
    expected = bytes.fromhex("330504080000000000000000000000000000003a")
    assert build_scene(0x08) == expected


def test_scene_breathe():
    """Breathe — newly added simple scene from Govee API."""
    expected = bytes.fromhex("3305040a00000000000000000000000000000038")
    assert build_scene(0x0A) == expected


def test_scene_energetic_simple():
    """Energetic — newly added simple scene from Govee API."""
    expected = bytes.fromhex("3305041000000000000000000000000000000022")
    assert build_scene(0x10) == expected


def test_scene_multi_byte_code():
    """Complex scene codes (>255) use little-endian byte order."""
    # e.g., code 2163 (Forest) → 0x0873 → bytes [0x73, 0x08]
    packet = build_scene(2163)
    assert packet[2] == 0x04  # scene sub-command
    assert packet[3] == 0x73  # low byte
    assert packet[4] == 0x08  # high byte
    assert len(packet) == 20
    assert xor_checksum(packet[:19]) == packet[19]


def test_empty_param_returns_single_packet():
    """Empty scenceParam means only the standard command."""
    packets = build_scene_multi("", 22)
    assert len(packets) == 1
    # Should be the standard scene command for code 22 (rainbow)
    assert packets[0] == build_scene(22)


def test_multi_packet_structure():
    """Multi-packet scene with real scenceParam data."""
    # Small base64 payload to test packet splitting
    # 20 bytes of data → after prefix_add (1 byte) = 21 bytes
    # + 2 bytes (0x01, num_lines) = 23 bytes total
    # 23 / 17 = 2 packets (ceil)
    raw = bytes(20)
    param_b64 = base64.b64encode(raw).decode()
    packets = build_scene_multi(param_b64, 100)

    # Should have a3 packets + 1 standard command at the end
    assert len(packets) > 1

    # All packets are 20 bytes
    for pkt in packets:
        assert len(pkt) == 20

    # First packet starts with a3 00
    assert packets[0][0] == 0xA3
    assert packets[0][1] == 0x00

    # Last a3 packet has index 0xFF
    assert packets[-2][0] == 0xA3
    assert packets[-2][1] == 0xFF

    # Final packet is the standard command
    assert packets[-1][0] == 0x33
    assert packets[-1][1] == 0x05
    assert packets[-1][2] == 0x04

    # All packets have valid checksums
    for pkt in packets:
        assert xor_checksum(pkt[:19]) == pkt[19]


def test_multi_packet_real_scene():
    """Test with real Forest scene data from Govee API for H617A."""
    forest_param = (
        "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8F"
        "AgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC"
        "7hQBAP8AAAAAAAAAAA=="
    )
    forest_code = 2163

    packets = build_scene_multi(forest_param, forest_code)

    # Should produce multiple a3 packets + 1 standard command
    assert len(packets) > 2

    for pkt in packets:
        assert len(pkt) == 20
        assert xor_checksum(pkt[:19]) == pkt[19]

    # First a3 packet: prefix=a3, index=00, then 0x01, num_lines, prefix_add(02), data...
    assert packets[0][0] == 0xA3
    assert packets[0][1] == 0x00
    assert packets[0][2] == 0x01  # multi-packet marker

    # Standard command at the end: 33 05 04 [code_lo] [code_hi]
    std = packets[-1]
    assert std[0] == 0x33
    assert std[1] == 0x05
    assert std[2] == 0x04
    # 2163 = 0x0873 → little-endian: 0x73, 0x08
    assert std[3] == 0x73
    assert std[4] == 0x08


def test_state_query():
    expected = bytes.fromhex("AA010000000000000000000000000000000000AB")
    assert build_state_query() == expected


def test_keep_alive_same_as_query():
    assert build_keep_alive() == build_state_query()


def test_state_query_length():
    assert len(build_state_query()) == 20


def test_brightness_query():
    expected = bytes.fromhex("AA040000000000000000000000000000000000AE")
    assert build_brightness_query() == expected


def test_color_mode_query():
    expected = bytes.fromhex("AA050000000000000000000000000000000000AF")
    assert build_color_mode_query() == expected


def test_warm_1000k():
    r, g, b = kelvin_to_rgb(1000)
    assert r == 255
    assert g > 0


def test_daylight_5500k():
    r, g, b = kelvin_to_rgb(5500)
    assert r == 255
    assert g > 200
    assert b > 200


def test_cool_10000k():
    _, _, b = kelvin_to_rgb(10000)
    assert b > 200


def test_output_range():
    for k in range(1000, 10001, 500):
        r, g, b = kelvin_to_rgb(k)
        assert 0 <= r <= 255, f"R={r} out of range at {k}K"
        assert 0 <= g <= 255, f"G={g} out of range at {k}K"
        assert 0 <= b <= 255, f"B={b} out of range at {k}K"


def test_clamp_low():
    r, g, b = kelvin_to_rgb(500)
    assert 0 <= r <= 255


def test_clamp_high():
    r, g, b = kelvin_to_rgb(20000)
    assert 0 <= r <= 255


def test_video_mode_default():
    packet = build_video_mode()
    assert len(packet) == 20
    assert packet[0] == 0x33
    assert packet[1] == 0x05
    assert packet[2] == 0x00  # VIDEO mode
    assert packet[3] == 0x01  # full_screen=True
    assert packet[4] == 0x00  # game_mode=False
    assert packet[5] == 100  # saturation=100


def test_video_mode_game():
    packet = build_video_mode(full_screen=False, game_mode=True, saturation=75)
    assert packet[3] == 0x00  # full_screen=False
    assert packet[4] == 0x01  # game_mode=True
    assert packet[5] == 75


def test_video_mode_saturation_clamp():
    packet = build_video_mode(saturation=200)
    assert packet[5] == 100
    packet2 = build_video_mode(saturation=-5)
    assert packet2[5] == 0


def test_video_mode_checksum():
    packet = build_video_mode()
    assert xor_checksum(packet[:19]) == packet[19]


def test_video_mode_length():
    assert len(build_video_mode()) == 20


def test_video_mode_sound_effects():
    packet = build_video_mode(sound_effects=True, sound_effects_softness=50)
    assert packet[6] == 0x01  # sound_effects flag
    assert packet[7] == 50  # softness
    assert len(packet) == 20
    assert xor_checksum(packet[:19]) == packet[19]


def test_video_mode_sound_effects_off_no_bytes():
    packet = build_video_mode(sound_effects=False)
    assert packet[6] == 0x00  # no flag byte appended, zero-padded


def test_video_mode_sound_effects_softness_clamp():
    packet = build_video_mode(sound_effects=True, sound_effects_softness=200)
    assert packet[7] == 100
    packet2 = build_video_mode(sound_effects=True, sound_effects_softness=-5)
    assert packet2[7] == 0


def test_video_mode_all_params():
    packet = build_video_mode(
        full_screen=False,
        game_mode=True,
        saturation=60,
        sound_effects=True,
        sound_effects_softness=75,
    )
    assert packet[2] == 0x00  # VIDEO
    assert packet[3] == 0x00  # partial
    assert packet[4] == 0x01  # game
    assert packet[5] == 60  # saturation
    assert packet[6] == 0x01  # sound_effects
    assert packet[7] == 75  # softness
    assert xor_checksum(packet[:19]) == packet[19]


def test_gradient_on():
    packet = build_gradient(True)
    assert packet[0] == 0x33
    assert packet[1] == 0x14
    assert packet[2] == 0x01
    assert len(packet) == 20


def test_gradient_off():
    packet = build_gradient(False)
    assert packet[2] == 0x00


def test_gradient_checksum():
    for on in (True, False):
        packet = build_gradient(on)
        assert xor_checksum(packet[:19]) == packet[19]


def test_without_color():
    packet = build_music_mode_with_color(0x05, sensitivity=80)
    assert packet[0] == 0x33
    assert packet[1] == 0x05
    assert packet[2] == 0x13
    assert packet[3] == 0x05  # energic
    assert packet[4] == 80  # sensitivity
    assert packet[5] == 0x00  # calm=False


def test_with_color():
    packet = build_music_mode_with_color(0x04, sensitivity=100, color=(255, 0, 128))
    assert packet[5] == 0x00  # calm=False
    assert packet[6] == 0x01  # has_color flag
    assert packet[7] == 255
    assert packet[8] == 0
    assert packet[9] == 128


def test_sensitivity_clamp():
    packet = build_music_mode_with_color(0x03, sensitivity=150)
    assert packet[4] == 100


def test_length_and_checksum():
    for color in [None, (0, 128, 255)]:
        packet = build_music_mode_with_color(0x05, color=color)
        assert len(packet) == 20
        assert xor_checksum(packet[:19]) == packet[19]


def test_calm_flag():
    packet = build_music_mode_with_color(0x03, sensitivity=80, calm=True)
    assert packet[4] == 80  # sensitivity
    assert packet[5] == 0x01  # calm=True
    assert xor_checksum(packet[:19]) == packet[19]


def test_calm_with_color():
    packet = build_music_mode_with_color(0x03, sensitivity=50, calm=True, color=(128, 64, 32))
    assert packet[5] == 0x01  # calm
    assert packet[6] == 0x01  # has_color
    assert packet[7] == 128
    assert packet[8] == 64
    assert packet[9] == 32


def test_calm_default_false():
    packet = build_music_mode_with_color(0x05)
    assert packet[5] == 0x00  # calm defaults to False


def test_parse_power_on():
    assert parse_power_response(bytes([0x01, 0x00]))


def test_parse_power_off():
    assert not parse_power_response(bytes([0x00, 0x00]))


def test_parse_brightness():
    assert parse_brightness_response(bytes([75, 0x00])) == 75


def test_parse_color_mode_video():
    parsed = parse_color_mode_response(bytes([0x00, 0x00, 0x01, 42, 0x01, 55]))
    assert parsed.effect == "video: game"
    assert not parsed.video_full_screen
    assert parsed.video_saturation == 42
    assert parsed.video_sound_effects
    assert parsed.video_sound_effects_softness == 55


def test_parse_color_mode_music_with_color():
    parsed = parse_color_mode_response(bytes([0x13, 0x04, 77, 0x00, 0x01, 1, 2, 3]))
    assert parsed.effect == "music: spectrum"
    assert parsed.music_sensitivity == 77
    assert parsed.music_color == (1, 2, 3)


def test_parse_color_mode_static_rgb():
    parsed = parse_color_mode_response(bytes([0x15, 0x01, 10, 20, 30]))
    assert parsed.effect is None
    assert parsed.rgb_color == (10, 20, 30)


def test_parse_color_mode_static_white_brightness():
    parsed = parse_color_mode_response(bytes([0x15, 0x02, 0x80]))
    assert parsed.white_brightness == 50


def test_parse_color_mode_empty_payload_raises():
    with pytest.raises(ValueError):
        parse_color_mode_response(bytes())


def test_packet_header_values():
    assert PacketHeader.COMMAND == 0x33
    assert PacketHeader.STATUS == 0xAA


def test_packet_type_values():
    assert PacketType.POWER == 0x01
    assert PacketType.BRIGHTNESS == 0x04
    assert PacketType.COLOR == 0x05
    assert PacketType.GRADIENT == 0x14


def test_color_mode_values():
    assert ColorMode.VIDEO == 0x00
    assert ColorMode.MUSIC == 0x13
    assert ColorMode.STATIC == 0x15
