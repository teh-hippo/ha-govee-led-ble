"""Govee BLE protocol — 20-byte packets with XOR checksum at byte 19."""

import base64
import math
from dataclasses import dataclass
from enum import IntEnum
from typing import cast

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


MUSIC_EFFECT_BY_ID: dict[int, str] = {
    0x05: "music: energic",
    0x03: "music: rhythm",
    0x04: "music: spectrum",
    0x06: "music: rolling",
}
MULTI_PACKET_PREFIX = 0xA3
SCENE_HEX_PREFIX_ADD = bytes([0x02])


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _get(payload: bytes, index: int) -> int | None:
    return payload[index] if len(payload) > index else None


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for part in data:
        checksum ^= part
    return checksum


def build_packet(cmd_type: int, action: int, params: list[int]) -> bytes:
    payload = bytearray([cmd_type, action, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


def build_power(on: bool) -> bytes:
    return build_packet(0x33, 0x01, [int(on)])


def build_brightness(percent: int) -> bytes:
    return build_packet(0x33, 0x04, [_clamp(percent, 0, 100)])


def build_color_rgb(r: int, g: int, b: int) -> bytes:
    return build_packet(
        0x33, 0x05, [0x15, 0x01, _clamp(r, 0, 255), _clamp(g, 0, 255), _clamp(b, 0, 255), 0, 0, 0, 0, 0, 0xFF, 0x7F]
    )


def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
    temp = _clamp(kelvin, 1000, 10000) / 100.0
    red = 255.0 if temp <= 66 else _clamp(int(329.698727446 * ((temp - 60) ** -0.1332047592)), 0, 255)
    green = (
        99.4708025861 * math.log(temp) - 161.1195681661
        if temp <= 66
        else 288.1221695283 * ((temp - 60) ** -0.0755148492)
    )
    blue = 255.0 if temp >= 66 else 0.0 if temp <= 19 else 138.5177312231 * math.log(temp - 10) - 305.0447927307
    return int(red), _clamp(int(green), 0, 255), _clamp(int(blue), 0, 255)


def build_color_temp(kelvin: int) -> bytes:
    return build_color_rgb(*kelvin_to_rgb(kelvin))


def build_scene(scene_id: int) -> bytes:
    width = max(1, (scene_id.bit_length() + 7) // 8)
    return build_packet(0x33, 0x05, [0x04, *scene_id.to_bytes(width, "little")])


def build_scene_multi(scene_param_b64: str, scene_code: int) -> list[bytes]:
    if not scene_param_b64:
        return [build_scene(scene_code)]
    data = SCENE_HEX_PREFIX_ADD + base64.b64decode(scene_param_b64)
    payload = bytes([0x01, math.ceil((len(data) + 2) / 17)]) + data
    chunks = [payload[index : index + 17] for index in range(0, len(payload), 17)]
    packets: list[bytes] = []
    for index, chunk in enumerate(chunks):
        packet = bytearray([MULTI_PACKET_PREFIX, 0xFF if index == len(chunks) - 1 else index, *chunk])
        packet = (packet + bytearray(19 - len(packet)))[:19]
        packet.append(xor_checksum(packet))
        packets.append(bytes(packet))
    return [*packets, build_scene(scene_code)]


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
    params = [ColorMode.VIDEO, int(full_screen), int(game_mode), _clamp(saturation, 0, 100)]
    if sound_effects:
        params.extend([0x01, _clamp(sound_effects_softness, 0, 100)])
    return build_packet(0x33, 0x05, params)


def build_music_mode_with_color(
    mode_id: int,
    sensitivity: int = 100,
    color: tuple[int, int, int] | None = None,
    calm: bool = False,
) -> bytes:
    params = [0x13, mode_id, _clamp(sensitivity, 0, 100), int(calm)]
    if color is not None:
        params.extend([0x01, *(_clamp(channel, 0, 255) for channel in color)])
    return build_packet(0x33, 0x05, params)


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


def parse_color_mode_response(payload: bytes) -> ParsedColorModeResponse:
    if not payload:
        raise ValueError("Color mode payload is empty")
    mode = payload[0]
    if mode == ColorMode.VIDEO:
        return ParsedColorModeResponse(
            effect="video: game" if bool(_get(payload, 2)) else "video: movie",
            video_full_screen=bool(v) if (v := _get(payload, 1)) is not None else None,
            video_saturation=_get(payload, 3),
            video_sound_effects=bool(v) if (v := _get(payload, 4)) is not None else None,
            video_sound_effects_softness=_get(payload, 5),
        )
    if mode == ColorMode.MUSIC:
        color_parts = (_get(payload, 5), _get(payload, 6), _get(payload, 7))
        music_color = (
            cast(tuple[int, int, int], color_parts) if _get(payload, 4) == 0x01 and None not in color_parts else None
        )
        return ParsedColorModeResponse(
            effect=MUSIC_EFFECT_BY_ID.get(_get(payload, 1) or -1),
            music_sensitivity=_get(payload, 2),
            music_color=music_color,
        )
    if mode != ColorMode.STATIC:
        return ParsedColorModeResponse()
    rgb_parts = (_get(payload, 2), _get(payload, 3), _get(payload, 4))
    rgb_color = cast(tuple[int, int, int], rgb_parts) if _get(payload, 1) == 0x01 and None not in rgb_parts else None
    return ParsedColorModeResponse(
        rgb_color=rgb_color,
        white_brightness=round((payload[2] * 100) / 255) if _get(payload, 1) == 0x02 and len(payload) > 2 else None,
    )
