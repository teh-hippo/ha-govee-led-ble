"""Unit tests for the Govee BLE protocol module."""

import os
import sys
import unittest

# Add the protocol module's directory to the path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "govee_ble_lights"))

from protocol import (
    ColorMode,
    PacketHeader,
    PacketType,
    build_brightness,
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
    kelvin_to_rgb,
    parse_brightness_response,
    parse_power_response,
    xor_checksum,
)


class TestChecksum(unittest.TestCase):
    def test_xor_all_zeros(self):
        self.assertEqual(xor_checksum(bytes(19)), 0x00)

    def test_xor_power_on(self):
        data = bytearray([0x33, 0x01, 0x01] + [0x00] * 16)
        self.assertEqual(xor_checksum(data), 0x33)

    def test_xor_power_off(self):
        data = bytearray([0x33, 0x01, 0x00] + [0x00] * 16)
        self.assertEqual(xor_checksum(data), 0x32)

    def test_xor_state_query(self):
        data = bytearray([0xAA, 0x01] + [0x00] * 17)
        self.assertEqual(xor_checksum(data), 0xAB)


class TestBuildPacket(unittest.TestCase):
    def test_packet_length(self):
        self.assertEqual(len(build_packet(0x33, 0x01, [0x01])), 20)

    def test_packet_checksum_valid(self):
        packet = build_packet(0x33, 0x01, [0x01])
        self.assertEqual(xor_checksum(packet[:19]), packet[19])

    def test_packet_padding(self):
        packet = build_packet(0x33, 0x01, [])
        for i in range(2, 19):
            self.assertEqual(packet[i], 0x00)

    def test_packet_truncates_long_params(self):
        params = list(range(20))
        packet = build_packet(0x33, 0x01, params)
        self.assertEqual(len(packet), 20)


class TestPower(unittest.TestCase):
    def test_power_on(self):
        expected = bytes.fromhex("3301010000000000000000000000000000000033")
        self.assertEqual(build_power(True), expected)

    def test_power_off(self):
        expected = bytes.fromhex("3301000000000000000000000000000000000032")
        self.assertEqual(build_power(False), expected)

    def test_power_length(self):
        self.assertEqual(len(build_power(True)), 20)
        self.assertEqual(len(build_power(False)), 20)


class TestBrightness(unittest.TestCase):
    def test_brightness_100(self):
        packet = build_brightness(100)
        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[0], 0x33)
        self.assertEqual(packet[1], 0x04)
        self.assertEqual(packet[2], 100)

    def test_brightness_0(self):
        self.assertEqual(build_brightness(0)[2], 0)

    def test_brightness_clamp_high(self):
        self.assertEqual(build_brightness(200)[2], 100)

    def test_brightness_clamp_low(self):
        self.assertEqual(build_brightness(-10)[2], 0)

    def test_brightness_checksum(self):
        packet = build_brightness(50)
        self.assertEqual(xor_checksum(packet[:19]), packet[19])


class TestColorRGB(unittest.TestCase):
    def test_color_red_segmented(self):
        packet = build_color_rgb(255, 0, 0)
        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[0], 0x33)
        self.assertEqual(packet[1], 0x05)
        self.assertEqual(packet[2], 0x15)  # segmented mode
        self.assertEqual(packet[3], 0x01)  # set color sub-command
        self.assertEqual(packet[4], 0xFF)  # R
        self.assertEqual(packet[5], 0x00)  # G
        self.assertEqual(packet[6], 0x00)  # B
        self.assertEqual(packet[12], 0xFF)  # seg_lo (all)
        self.assertEqual(packet[13], 0x7F)  # seg_hi (15 segments)

    def test_color_matches_known_format(self):
        packet = build_color_rgb(0xFF, 0x00, 0x00)
        self.assertEqual(
            packet[:14],
            bytes(
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
            ),
        )

    def test_color_clamp(self):
        packet = build_color_rgb(300, -10, 128)
        self.assertEqual(packet[4], 255)
        self.assertEqual(packet[5], 0)
        self.assertEqual(packet[6], 128)


class TestColorTemp(unittest.TestCase):
    def test_packet_length(self):
        self.assertEqual(len(build_color_temp(4000)), 20)

    def test_uses_segmented_mode(self):
        packet = build_color_temp(4000)
        self.assertEqual(packet[2], 0x15)

    def test_warm_has_high_red(self):
        r, g, b = kelvin_to_rgb(2700)
        self.assertEqual(r, 255)
        self.assertGreater(g, 100)
        self.assertLess(b, g)

    def test_cool_has_high_blue(self):
        r, g, b = kelvin_to_rgb(6500)
        self.assertEqual(r, 255)
        self.assertGreater(b, 200)


class TestScene(unittest.TestCase):
    def test_scene_sunrise(self):
        expected = bytes.fromhex("3305040000000000000000000000000000000032")
        self.assertEqual(build_scene(0x00), expected)

    def test_scene_sunset(self):
        expected = bytes.fromhex("3305040100000000000000000000000000000033")
        self.assertEqual(build_scene(0x01), expected)

    def test_scene_movie(self):
        expected = bytes.fromhex("3305040400000000000000000000000000000036")
        self.assertEqual(build_scene(0x04), expected)

    def test_scene_rainbow(self):
        expected = bytes.fromhex("3305041600000000000000000000000000000024")
        self.assertEqual(build_scene(0x16), expected)

    def test_scene_twinkle(self):
        """Twinkle (was 'blinking' — renamed per Govee API)."""
        expected = bytes.fromhex("330504080000000000000000000000000000003a")
        self.assertEqual(build_scene(0x08), expected)

    def test_scene_breathe(self):
        """Breathe — newly added simple scene from Govee API."""
        expected = bytes.fromhex("3305040a00000000000000000000000000000038")
        self.assertEqual(build_scene(0x0A), expected)

    def test_scene_energetic_simple(self):
        """Energetic — newly added simple scene from Govee API."""
        expected = bytes.fromhex("3305041000000000000000000000000000000022")
        self.assertEqual(build_scene(0x10), expected)

    def test_scene_multi_byte_code(self):
        """Complex scene codes (>255) use little-endian byte order."""
        # e.g., code 2163 (Forest) → 0x0873 → bytes [0x73, 0x08]
        packet = build_scene(2163)
        self.assertEqual(packet[2], 0x04)  # scene sub-command
        self.assertEqual(packet[3], 0x73)  # low byte
        self.assertEqual(packet[4], 0x08)  # high byte
        self.assertEqual(len(packet), 20)
        self.assertEqual(xor_checksum(packet[:19]), packet[19])


class TestSceneMulti(unittest.TestCase):
    def test_empty_param_returns_single_packet(self):
        """Empty scenceParam means only the standard command."""
        packets = build_scene_multi("", 22)
        self.assertEqual(len(packets), 1)
        # Should be the standard scene command for code 22 (rainbow)
        self.assertEqual(packets[0], build_scene(22))

    def test_multi_packet_structure(self):
        """Multi-packet scene with real scenceParam data."""
        # Small base64 payload to test packet splitting
        import base64

        # 20 bytes of data → after prefix_add (1 byte) = 21 bytes
        # + 2 bytes (0x01, num_lines) = 23 bytes total
        # 23 / 17 = 2 packets (ceil)
        raw = bytes(20)
        param_b64 = base64.b64encode(raw).decode()
        packets = build_scene_multi(param_b64, 100)

        # Should have a3 packets + 1 standard command at the end
        self.assertGreater(len(packets), 1)

        # All packets are 20 bytes
        for pkt in packets:
            self.assertEqual(len(pkt), 20)

        # First packet starts with a3 00
        self.assertEqual(packets[0][0], 0xA3)
        self.assertEqual(packets[0][1], 0x00)

        # Last a3 packet has index 0xFF
        self.assertEqual(packets[-2][0], 0xA3)
        self.assertEqual(packets[-2][1], 0xFF)

        # Final packet is the standard command
        self.assertEqual(packets[-1][0], 0x33)
        self.assertEqual(packets[-1][1], 0x05)
        self.assertEqual(packets[-1][2], 0x04)

        # All packets have valid checksums
        for pkt in packets:
            self.assertEqual(xor_checksum(pkt[:19]), pkt[19])

    def test_multi_packet_real_scene(self):
        """Test with real Forest scene data from Govee API for H617A."""
        forest_param = (
            "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8F"
            "AgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC"
            "7hQBAP8AAAAAAAAAAA=="
        )
        forest_code = 2163

        packets = build_scene_multi(forest_param, forest_code)

        # Should produce multiple a3 packets + 1 standard command
        self.assertGreater(len(packets), 2)

        for pkt in packets:
            self.assertEqual(len(pkt), 20)
            self.assertEqual(xor_checksum(pkt[:19]), pkt[19])

        # First a3 packet: prefix=a3, index=00, then 0x01, num_lines, prefix_add(02), data...
        self.assertEqual(packets[0][0], 0xA3)
        self.assertEqual(packets[0][1], 0x00)
        self.assertEqual(packets[0][2], 0x01)  # multi-packet marker

        # Standard command at the end: 33 05 04 [code_lo] [code_hi]
        std = packets[-1]
        self.assertEqual(std[0], 0x33)
        self.assertEqual(std[1], 0x05)
        self.assertEqual(std[2], 0x04)
        # 2163 = 0x0873 → little-endian: 0x73, 0x08
        self.assertEqual(std[3], 0x73)
        self.assertEqual(std[4], 0x08)


class TestStateQuery(unittest.TestCase):
    def test_state_query(self):
        expected = bytes.fromhex("AA010000000000000000000000000000000000AB")
        self.assertEqual(build_state_query(), expected)

    def test_keep_alive_same_as_query(self):
        self.assertEqual(build_keep_alive(), build_state_query())

    def test_state_query_length(self):
        self.assertEqual(len(build_state_query()), 20)


class TestKelvinToRGB(unittest.TestCase):
    def test_warm_1000k(self):
        r, g, b = kelvin_to_rgb(1000)
        self.assertEqual(r, 255)
        self.assertGreater(g, 0)

    def test_daylight_5500k(self):
        r, g, b = kelvin_to_rgb(5500)
        self.assertEqual(r, 255)
        self.assertGreater(g, 200)
        self.assertGreater(b, 200)

    def test_cool_10000k(self):
        _, _, b = kelvin_to_rgb(10000)
        self.assertGreater(b, 200)

    def test_output_range(self):
        for k in range(1000, 10001, 500):
            r, g, b = kelvin_to_rgb(k)
            self.assertTrue(0 <= r <= 255, f"R={r} out of range at {k}K")
            self.assertTrue(0 <= g <= 255, f"G={g} out of range at {k}K")
            self.assertTrue(0 <= b <= 255, f"B={b} out of range at {k}K")

    def test_clamp_low(self):
        r, g, b = kelvin_to_rgb(500)
        self.assertTrue(0 <= r <= 255)

    def test_clamp_high(self):
        r, g, b = kelvin_to_rgb(20000)
        self.assertTrue(0 <= r <= 255)


class TestAllPacketsLength(unittest.TestCase):
    """Verify every command builder produces exactly 20 bytes."""

    def test_power_on(self):
        self.assertEqual(len(build_power(True)), 20)

    def test_power_off(self):
        self.assertEqual(len(build_power(False)), 20)

    def test_brightness(self):
        self.assertEqual(len(build_brightness(50)), 20)

    def test_color_rgb(self):
        self.assertEqual(len(build_color_rgb(128, 128, 128)), 20)

    def test_color_temp(self):
        self.assertEqual(len(build_color_temp(4000)), 20)

    def test_scene(self):
        self.assertEqual(len(build_scene(0x00)), 20)

    def test_state_query(self):
        self.assertEqual(len(build_state_query()), 20)

    def test_keep_alive(self):
        self.assertEqual(len(build_keep_alive()), 20)


if __name__ == "__main__":
    unittest.main()


class TestVideoMode(unittest.TestCase):
    def test_video_mode_default(self):
        packet = build_video_mode()
        self.assertEqual(len(packet), 20)
        self.assertEqual(packet[0], 0x33)
        self.assertEqual(packet[1], 0x05)
        self.assertEqual(packet[2], 0x00)  # VIDEO mode
        self.assertEqual(packet[3], 0x01)  # full_screen=True
        self.assertEqual(packet[4], 0x00)  # game_mode=False
        self.assertEqual(packet[5], 100)  # saturation=100

    def test_video_mode_game(self):
        packet = build_video_mode(full_screen=False, game_mode=True, saturation=75)
        self.assertEqual(packet[3], 0x00)  # full_screen=False
        self.assertEqual(packet[4], 0x01)  # game_mode=True
        self.assertEqual(packet[5], 75)

    def test_video_mode_saturation_clamp(self):
        packet = build_video_mode(saturation=200)
        self.assertEqual(packet[5], 100)
        packet2 = build_video_mode(saturation=-5)
        self.assertEqual(packet2[5], 0)

    def test_video_mode_checksum(self):
        packet = build_video_mode()
        self.assertEqual(xor_checksum(packet[:19]), packet[19])

    def test_video_mode_length(self):
        self.assertEqual(len(build_video_mode()), 20)


class TestGradient(unittest.TestCase):
    def test_gradient_on(self):
        packet = build_gradient(True)
        self.assertEqual(packet[0], 0x33)
        self.assertEqual(packet[1], 0x14)
        self.assertEqual(packet[2], 0x01)
        self.assertEqual(len(packet), 20)

    def test_gradient_off(self):
        packet = build_gradient(False)
        self.assertEqual(packet[2], 0x00)

    def test_gradient_checksum(self):
        for on in (True, False):
            packet = build_gradient(on)
            self.assertEqual(xor_checksum(packet[:19]), packet[19])


class TestMusicModeWithColor(unittest.TestCase):
    def test_without_color(self):
        packet = build_music_mode_with_color(0x05, sensitivity=80)
        self.assertEqual(packet[0], 0x33)
        self.assertEqual(packet[1], 0x05)
        self.assertEqual(packet[2], 0x13)
        self.assertEqual(packet[3], 0x05)  # energic
        self.assertEqual(packet[4], 80)  # sensitivity
        self.assertEqual(packet[5], 0x00)  # no color flag

    def test_with_color(self):
        packet = build_music_mode_with_color(0x04, sensitivity=100, color=(255, 0, 128))
        self.assertEqual(packet[5], 0x01)  # has_color flag
        self.assertEqual(packet[6], 255)
        self.assertEqual(packet[7], 0)
        self.assertEqual(packet[8], 128)

    def test_sensitivity_clamp(self):
        packet = build_music_mode_with_color(0x03, sensitivity=150)
        self.assertEqual(packet[4], 100)

    def test_length_and_checksum(self):
        for color in [None, (0, 128, 255)]:
            packet = build_music_mode_with_color(0x05, color=color)
            self.assertEqual(len(packet), 20)
            self.assertEqual(xor_checksum(packet[:19]), packet[19])


class TestResponseParsers(unittest.TestCase):
    def test_parse_power_on(self):
        self.assertTrue(parse_power_response(bytes([0x01, 0x00])))

    def test_parse_power_off(self):
        self.assertFalse(parse_power_response(bytes([0x00, 0x00])))

    def test_parse_brightness(self):
        self.assertEqual(parse_brightness_response(bytes([75, 0x00])), 75)


class TestEnums(unittest.TestCase):
    def test_packet_header_values(self):
        self.assertEqual(PacketHeader.COMMAND, 0x33)
        self.assertEqual(PacketHeader.STATUS, 0xAA)

    def test_packet_type_values(self):
        self.assertEqual(PacketType.POWER, 0x01)
        self.assertEqual(PacketType.BRIGHTNESS, 0x04)
        self.assertEqual(PacketType.COLOR, 0x05)
        self.assertEqual(PacketType.GRADIENT, 0x14)

    def test_color_mode_values(self):
        self.assertEqual(ColorMode.VIDEO, 0x00)
        self.assertEqual(ColorMode.MUSIC, 0x13)
        self.assertEqual(ColorMode.STATIC, 0x15)
