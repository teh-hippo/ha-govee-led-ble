"""Govee BLE protocol — 20-byte packets with XOR checksum at byte 19."""

import base64  # noqa: E401
import math
from dataclasses import dataclass
from enum import IntEnum

WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


class PacketHeader(IntEnum):
    COMMAND = 0x33
    STATUS = 0xAA


class PacketType(IntEnum):
    POWER = 0x01
    BRIGHTNESS = 0x04
    COLOR = 0x05


class ColorMode(IntEnum):
    VIDEO = 0x00
    MUSIC = 0x13
    STATIC = 0x15


# fmt: off
MUSIC_EFFECT_BY_ID: dict[int, str] = {0x05: "music: energic", 0x03: "music: rhythm",
                                       0x04: "music: spectrum", 0x06: "music: rolling"}
# fmt: on
MULTI_PACKET_PREFIX = 0xA3
SCENE_HEX_PREFIX_ADD = bytes([0x02])


def xor_checksum(data: bytes | bytearray) -> int:
    r = 0
    for b in data:
        r ^= b
    return r


def build_packet(cmd_type: int, action: int, params: list[int]) -> bytes:
    data = bytearray([cmd_type, action] + params)[:19]
    data.extend(b"\x00" * (19 - len(data)))
    data.append(xor_checksum(data))
    return bytes(data)


def build_power(on: bool) -> bytes:
    return build_packet(0x33, 0x01, [0x01 if on else 0x00])


def build_brightness(percent: int) -> bytes:
    return build_packet(0x33, 0x04, [max(0, min(100, percent))])


def build_color_rgb(r: int, g: int, b: int) -> bytes:
    r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
    return build_packet(0x33, 0x05, [0x15, 0x01, r, g, b, 0, 0, 0, 0, 0, 0xFF, 0x7F])


def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
    temp = max(1000, min(10000, kelvin)) / 100.0
    red = 255.0 if temp <= 66 else max(0.0, min(255.0, 329.698727446 * ((temp - 60) ** -0.1332047592)))
    green = (
        99.4708025861 * math.log(temp) - 161.1195681661
        if temp <= 66
        else 288.1221695283 * ((temp - 60) ** -0.0755148492)
    )
    green = max(0.0, min(255.0, green))
    blue = (
        255.0
        if temp >= 66
        else (0.0 if temp <= 19 else max(0.0, min(255.0, 138.5177312231 * math.log(temp - 10) - 305.0447927307)))
    )
    return int(red), int(green), int(blue)


def build_color_temp(kelvin: int) -> bytes:
    return build_color_rgb(*kelvin_to_rgb(kelvin))


def build_scene(scene_id: int) -> bytes:
    code_bytes = [0x00] if scene_id == 0 else []
    code = scene_id
    while code > 0:
        code_bytes.append(code & 0xFF)
        code >>= 8
    return build_packet(0x33, 0x05, [0x04] + code_bytes)


def build_scene_multi(scene_param_b64: str, scene_code: int) -> list[bytes]:
    if not scene_param_b64:
        return [build_scene(scene_code)]
    data = SCENE_HEX_PREFIX_ADD + base64.b64decode(scene_param_b64)
    num_lines = math.ceil((len(data) + 2) / 17)
    payload = bytes([0x01, num_lines]) + data
    chunks = [payload[i : i + 17] for i in range(0, len(payload), 17)]
    packets: list[bytes] = []
    for i, chunk in enumerate(chunks):
        pkt = bytearray([MULTI_PACKET_PREFIX, 0xFF if i == len(chunks) - 1 else i])
        pkt.extend(chunk)
        pkt = (pkt + bytearray(19 - len(pkt)))[:19]
        pkt.append(xor_checksum(pkt))
        packets.append(bytes(pkt))
    packets.append(build_scene(scene_code))
    return packets


STATE_QUERY = build_packet(PacketHeader.STATUS, PacketType.POWER, [])
BRIGHTNESS_QUERY = build_packet(PacketHeader.STATUS, PacketType.BRIGHTNESS, [])
COLOR_MODE_QUERY = build_packet(PacketHeader.STATUS, PacketType.COLOR, [])
KEEP_ALIVE = STATE_QUERY


def build_video_mode(
    full_screen: bool = True,
    game_mode: bool = False,
    saturation: int = 100,
    sound_effects: bool = False,
    sound_effects_softness: int = 0,
) -> bytes:
    saturation = max(0, min(100, saturation))
    params = [ColorMode.VIDEO, int(full_screen), int(game_mode), saturation]
    if sound_effects:
        params.extend([0x01, max(0, min(100, sound_effects_softness))])
    return build_packet(0x33, 0x05, params)


def build_music_mode_with_color(
    mode_id: int,
    sensitivity: int = 100,
    color: tuple[int, int, int] | None = None,
    calm: bool = False,
) -> bytes:
    sensitivity = max(0, min(100, sensitivity))
    params = [0x13, mode_id, sensitivity, int(calm)]
    if color is not None:
        r, g, b = color
        params.extend([0x01, max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))])
    return build_packet(0x33, 0x05, params)


def parse_power_response(payload: bytes) -> bool:
    return bool(payload[0])


def parse_brightness_response(payload: bytes) -> int:
    return payload[0]


@dataclass(frozen=True)
class ParsedColorModeResponse:
    effect: str | None = None
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    music_sensitivity: int | None = None
    music_color: tuple[int, int, int] | None = None
    rgb_color: tuple[int, int, int] | None = None
    white_brightness: int | None = None


# fmt: off
def parse_color_mode_response(payload: bytes) -> ParsedColorModeResponse:
    if not payload:
        raise ValueError("Color mode payload is empty")
    mode, parsed = payload[0], ParsedColorModeResponse
    if mode == ColorMode.VIDEO:
        return parsed(effect="video: game" if (len(payload) > 2 and bool(payload[2])) else "video: movie",
                 video_full_screen=bool(payload[1]) if len(payload) > 1 else None,
                 video_saturation=payload[3] if len(payload) > 3 else None,
                 video_sound_effects=bool(payload[4]) if len(payload) > 4 else None,
                 video_sound_effects_softness=payload[5] if len(payload) > 5 else None)
    if mode == ColorMode.MUSIC:
        color = (payload[5], payload[6], payload[7]) if len(payload) > 7 and payload[4] == 0x01 else None
        return parsed(effect=MUSIC_EFFECT_BY_ID.get(payload[1]) if len(payload) > 1 else None,
                 music_sensitivity=payload[2] if len(payload) > 2 else None, music_color=color)
    if mode == ColorMode.STATIC:
        return parsed(
            rgb_color=(payload[2], payload[3], payload[4]) if len(payload) > 4 and payload[1] == 0x01 else None,
            white_brightness=round(payload[2] * 100 / 255) if len(payload) > 2 and payload[1] == 0x02 else None,
        )
    return parsed()
# fmt: on
