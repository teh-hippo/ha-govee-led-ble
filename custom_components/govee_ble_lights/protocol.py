"""Govee BLE protocol implementation.

Packet format: 20 bytes, XOR checksum at byte 19.
Commands use Write Without Response (response=False in bleak).
Supports H617A, H6199, and future models sharing the same base protocol.
"""

import base64
import math
from enum import IntEnum

# BLE UUIDs (shared across all known Govee BLE models)
WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


# --- Packet types ---


class PacketHeader(IntEnum):
    """First byte of every packet."""

    COMMAND = 0x33
    STATUS = 0xAA


class PacketType(IntEnum):
    """Second byte — identifies the command domain."""

    POWER = 0x01
    BRIGHTNESS = 0x04
    COLOR = 0x05
    GRADIENT = 0x14


class ColorMode(IntEnum):
    """Third byte of color packets (0x33 0x05 [mode])."""

    VIDEO = 0x00
    MUSIC = 0x13
    STATIC = 0x15


# Multi-packet scene prefix byte (0xA3)
MULTI_PACKET_PREFIX = 0xA3

# Model-specific multi-packet parameters (from AlgoClaw/Govee analysis).
SCENE_HEX_PREFIX_ADD = bytes([0x02])


def xor_checksum(data: bytes) -> int:
    """XOR all bytes together to produce checksum."""
    checksum = 0
    for b in data:
        checksum ^= b
    return checksum


def build_packet(cmd_type: int, action: int, params: list[int]) -> bytes:
    """Build a 20-byte Govee BLE command packet.

    Args:
        cmd_type: Header byte (0x33 for commands, 0xAA for queries).
        action: Command byte.
        params: Payload bytes (zero-padded to fill 19 bytes).

    Returns:
        20-byte packet with XOR checksum at byte 19.
    """
    data = bytearray([cmd_type, action] + params)
    data = data[:19]  # truncate if too long
    while len(data) < 19:
        data.append(0x00)
    data.append(xor_checksum(data))
    return bytes(data)


def build_power(on: bool) -> bytes:
    """Build power on/off command."""
    return build_packet(0x33, 0x01, [0x01 if on else 0x00])


def build_brightness(percent: int) -> bytes:
    """Build brightness command (0-100 percentage scale)."""
    percent = max(0, min(100, percent))
    return build_packet(0x33, 0x04, [percent])


def build_color_rgb(r: int, g: int, b: int) -> bytes:
    """Build color command using SEGMENTED mode (0x15).

    Sets all 15 segments to the specified color.
    Format: 33 05 15 01 RR GG BB 00 00 00 00 00 FF 7F 00 00 00 00 00 [xor]
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    params = [0x15, 0x01, r, g, b, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x7F]
    return build_packet(0x33, 0x05, params)


def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
    """Convert color temperature in Kelvin to approximate RGB.

    Uses the Tanner Helland algorithm. Clamped to 1000-10000K range.
    """
    kelvin = max(1000, min(10000, kelvin))
    temp = kelvin / 100.0

    # Red
    if temp <= 66:
        red = 255.0
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        red = max(0.0, min(255.0, red))

    # Green
    if temp <= 66:
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
    green = max(0.0, min(255.0, green))

    # Blue
    if temp >= 66:
        blue = 255.0
    elif temp <= 19:
        blue = 0.0
    else:
        blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307
        blue = max(0.0, min(255.0, blue))

    return int(red), int(green), int(blue)


def build_color_temp(kelvin: int) -> bytes:
    """Build color temperature command by converting Kelvin to RGB.

    No native color temp BLE command exists, so we convert to RGB
    and use the segmented color mode.
    """
    r, g, b = kelvin_to_rgb(kelvin)
    return build_color_rgb(r, g, b)


def build_scene(scene_id: int) -> bytes:
    """Build scene selection command (standard/modeCmd).

    Format: 33 05 04 [code_byte(s)] 00...00 [xor]
    For simple scenes, scene_id fits in one byte.
    For complex scenes, scene_id is little-endian multi-byte.
    """
    code_bytes = []
    code = scene_id
    if code == 0:
        code_bytes = [0x00]
    else:
        while code > 0:
            code_bytes.append(code & 0xFF)
            code >>= 8
    return build_packet(0x33, 0x05, [0x04] + code_bytes)


def build_scene_multi(scene_param_b64: str, scene_code: int) -> list[bytes]:
    """Build multi-packet scene command sequence.

    Implements the AlgoClaw/Govee v1.2 multi-packet protocol for complex
    scenes that include scenceParam data from the Govee API.

    Args:
        scene_param_b64: Base64-encoded scenceParam from Govee API.
        scene_code: Scene code (decimal) from Govee API lightEffects.sceneCode.

    Returns:
        List of 20-byte packets to send in order.
    """
    if not scene_param_b64:
        # Empty scenceParam — only the standard command is needed
        return [build_scene(scene_code)]

    param_hex = base64.b64decode(scene_param_b64)

    data = SCENE_HEX_PREFIX_ADD + param_hex

    # Prepend 0x01 and num_lines
    # Each a3 packet carries 17 bytes of payload (20 - prefix(1) - index(1) - checksum(1))
    total_len = len(data) + 2  # +2 for the 0x01 and num_lines bytes
    num_lines = math.ceil(total_len / 17)
    payload = bytes([0x01, num_lines]) + data

    # Split payload into 17-byte chunks
    chunks = []
    for i in range(0, len(payload), 17):
        chunks.append(payload[i : i + 17])

    # Build a3 packets with line indices
    packets: list[bytes] = []
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1:
            line_idx = 0xFF
        else:
            line_idx = i
        pkt = bytearray([MULTI_PACKET_PREFIX, line_idx])
        pkt.extend(chunk)
        # Pad to 19 bytes and add checksum
        while len(pkt) < 19:
            pkt.append(0x00)
        pkt = pkt[:19]
        pkt.append(xor_checksum(pkt))
        packets.append(bytes(pkt))

    # Append the standard command
    packets.append(build_scene(scene_code))
    return packets


def build_state_query() -> bytes:
    """Build state query packet.

    Format: AA 01 00...00 AB
    """
    return build_packet(0xAA, 0x01, [])


def build_keep_alive() -> bytes:
    """Build keep-alive packet (same as state query)."""
    return build_state_query()


# --- H6199-specific commands ---


def build_video_mode(
    full_screen: bool = True,
    game_mode: bool = False,
    saturation: int = 100,
) -> bytes:
    """Build video/camera sync mode command.

    The device's onboard camera reads the TV screen and drives the LEDs.
    Format: 33 05 00 [full_screen] [game_mode] [saturation] 00...00 [xor]
    """
    saturation = max(0, min(100, saturation))
    params = [
        ColorMode.VIDEO,
        0x01 if full_screen else 0x00,
        0x01 if game_mode else 0x00,
        saturation,
    ]
    return build_packet(0x33, 0x05, params)


def build_gradient(on: bool) -> bytes:
    """Build gradient toggle command.

    Enables smooth color blending across segments (vs. hard boundaries).
    Format: 33 14 01/00 00...00 [xor]
    """
    return build_packet(0x33, PacketType.GRADIENT, [0x01 if on else 0x00])


def build_music_mode_with_color(
    mode_id: int,
    sensitivity: int = 100,
    color: tuple[int, int, int] | None = None,
) -> bytes:
    """Build music mode command with optional accent color.

    Format: 33 05 13 [mode_id] [sensitivity] [has_color] [R] [G] [B] 00...00 [xor]
    """
    sensitivity = max(0, min(100, sensitivity))
    params = [0x13, mode_id, sensitivity]
    if color is not None:
        r, g, b = color
        params.extend([0x01, max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))])
    return build_packet(0x33, 0x05, params)


# --- State response parsing (for models with notify support) ---


def parse_power_response(payload: bytes) -> bool:
    """Parse power state from status response payload."""
    return bool(payload[0])


def parse_brightness_response(payload: bytes) -> int:
    """Parse brightness percentage from status response payload."""
    return payload[0]
