"""Govee H617A BLE protocol implementation.

Packet format: 20 bytes, XOR checksum at byte 19.
Commands use Write Without Response (response=False in bleak).
"""

import base64
import math

# BLE UUIDs
SERVICE_UUID = "00010203-0405-0607-0809-0a0b0c0d1910"
WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"

# Simple scene IDs — single-packet scenes from Govee API for H617A.
# These use sceneType=0 with empty scenceParam (no multi-packet needed).
SCENE_IDS: dict[str, int] = {
    "sunrise": 0x00,
    "sunset": 0x01,
    "movie": 0x04,
    "romantic": 0x07,
    "twinkle": 0x08,
    "candlelight": 0x09,
    "breathe": 0x0A,
    "energetic": 0x10,
    "rainbow": 0x16,
}

# Multi-packet scene prefix byte (0xA3 for H617A)
MULTI_PACKET_PREFIX = 0xA3

# H617A model-specific parameters (from AlgoClaw/Govee analysis).
# scenceParam data is prefixed with this before splitting into packets.
H617A_HEX_PREFIX_ADD = bytes([0x02])
# No prefix to remove from scenceParam for H617A (empty string in API data).
H617A_HEX_PREFIX_REMOVE = b""

# Music mode v2 IDs (command: 0x33 0x05 0x13 [id] 0x63)
MUSIC_MODE_IDS: dict[str, int] = {
    "rhythm": 0x03,
    "spectrum": 0x04,
    "energetic": 0x05,
    "rolling": 0x06,
    "separation": 0x32,
}


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
    """Build brightness command (0-100 percentage scale for H617A)."""
    percent = max(0, min(100, percent))
    return build_packet(0x33, 0x04, [percent])


def build_color_rgb(r: int, g: int, b: int) -> bytes:
    """Build color command using SEGMENTED mode (0x15) for H617A.

    Sets all 15 segments to the specified color.
    Format: 33 05 15 01 RR GG BB 00 00 00 00 00 FF 7F 00 00 00 00 00 [xor]
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    params = [0x15, 0x01, r, g, b, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0x7F]
    return build_packet(0x33, 0x05, params)


def build_color_rgb_simple(r: int, g: int, b: int) -> bytes:
    """Build color command using simple mode (0x02) for comparison testing.

    This mode may NOT work on H617A (which requires segmented 0x15).
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return build_packet(0x33, 0x05, [0x02, r, g, b])


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

    H617A has no native color temp BLE command, so we convert to RGB
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

    # Apply model-specific prefix transforms
    data = param_hex
    if H617A_HEX_PREFIX_REMOVE and data.startswith(H617A_HEX_PREFIX_REMOVE):
        data = data[len(H617A_HEX_PREFIX_REMOVE) :]
    data = H617A_HEX_PREFIX_ADD + data

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


def build_music_mode(mode_id: int, sensitivity: int = 0x63) -> bytes:
    """Build music mode v2 command.

    Format: 33 05 13 [mode_id] [sensitivity] 00...00 [xor]
    """
    return build_packet(0x33, 0x05, [0x13, mode_id, sensitivity])


def build_segment_color(r: int, g: int, b: int, segments: list[int]) -> bytes:
    """Build per-segment color command.

    Args:
        r, g, b: Color values 0-255.
        segments: List of segment numbers (1-15) to apply color to.

    Segment bitmask: bits 0-7 in low byte (segs 1-8),
                     bits 0-6 in high byte (segs 9-15).
    """
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    mask = 0
    for seg in segments:
        if 1 <= seg <= 15:
            mask |= 1 << (seg - 1)
    seg_lo = mask & 0xFF
    seg_hi = (mask >> 8) & 0xFF
    params = [0x15, 0x01, r, g, b, 0x00, 0x00, 0x00, 0x00, 0x00, seg_lo, seg_hi]
    return build_packet(0x33, 0x05, params)


def build_state_query() -> bytes:
    """Build state query packet.

    Format: AA 01 00...00 AB
    """
    return build_packet(0xAA, 0x01, [])


def build_keep_alive() -> bytes:
    """Build keep-alive packet (same as state query)."""
    return build_state_query()
