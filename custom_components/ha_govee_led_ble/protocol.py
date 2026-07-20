"""Govee BLE protocol — 20-byte packets with XOR checksum at byte 19."""

import base64
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, IntEnum, auto
from typing import cast

from .const import MUSIC_MODE_SLUGS
from .custom_effects import (
    RGB,
    ComboContent,
    EffectContent,
    EffectValidationError,
    FlatContent,
    SegmentContent,
    SketchContent,
    VibrantContent,
)
from .scenes import SCENES

WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


COMMAND_HEADER = 0x33
STATUS_HEADER = 0xAA
POWER_PACKET_TYPE = 0x01
BRIGHTNESS_PACKET_TYPE = 0x04
COLOR_PACKET_TYPE = 0x05
FIRMWARE_PACKET_TYPE = 0x06
HARDWARE_PACKET_TYPE = 0x07
COLOR_MODE_SCENE = 0x04
COLOR_MODE_VIDEO = 0x00
COLOR_MODE_MUSIC = 0x13
COLOR_MODE_STATIC = 0x15
COLOR_MODE_DIY = 0x0A
DEFAULT_DIY_SLOT = 0xF0
SKETCH_DIY_SLOT = 0x20
VIBRANT_DIY_SLOT = 0x84


MUSIC_SLUG_BY_ID: dict[int, str] = {code: slug for slug, code in MUSIC_MODE_SLUGS.items()}
RHYTHM_MODE_ID = MUSIC_MODE_SLUGS["rhythm"]
SCENE_EFFECT_BY_ID: dict[int, str] = {scene.code: name for name, scene in SCENES.items()}
MULTI_PACKET_PREFIX = 0xA3


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _get(payload: bytes, index: int) -> int | None:
    return payload[index] if len(payload) > index else None


def xor_checksum(data: bytes | bytearray) -> int:
    checksum = 0
    for part in data:
        checksum ^= part
    return checksum


def split_status_frame(frame: bytes) -> tuple[int, bytes] | None:
    """Split an incoming status notification into ``(domain, payload)``.

    Returns ``None`` for frames shorter than three bytes or without the status header.
    A full 20-byte frame whose trailing checksum verifies drops that checksum byte; any
    other (loose) frame keeps everything after the domain byte.
    """
    if len(frame) < 3 or frame[0] != STATUS_HEADER:
        return None
    domain = frame[1]
    if len(frame) == 20 and xor_checksum(frame[:-1]) == frame[-1]:
        return domain, bytes(frame[2:-1])
    return domain, bytes(frame[2:])


def build_packet(cmd_type: int, action: int, params: list[int]) -> bytes:
    payload = bytearray([cmd_type, action, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


def build_power(on: bool) -> bytes:
    return build_packet(0x33, 0x01, [int(on)])


def build_brightness(percent: int) -> bytes:
    return build_packet(0x33, 0x04, [_clamp(percent, 0, 100)])


SEGMENT_COUNT = 15
ALL_SEGMENTS: tuple[int, ...] = tuple(range(1, SEGMENT_COUNT + 1))
ALL_SEGMENTS_MASK = 0x7FFF

type SegmentColorGroup = tuple[Iterable[int], tuple[int, int, int]]


def segments_to_mask(segments: Iterable[int]) -> int:
    """Map 1-based segment indices to the 15-bit segment mask (segment k -> bit k-1)."""
    selected = set(segments)
    if not selected:
        raise ValueError("no segments selected")
    mask = 0
    for segment in selected:
        if not 1 <= segment <= SEGMENT_COUNT:
            raise ValueError(f"segment {segment} out of range 1..{SEGMENT_COUNT}")
        mask |= 1 << (segment - 1)
    return mask


def build_segment_color(segments: Iterable[int], r: int, g: int, b: int) -> bytes:
    mask = segments_to_mask(segments)
    lo, hi = mask & 0xFF, (mask >> 8) & 0xFF
    return build_packet(
        0x33, 0x05, [0x15, 0x01, _clamp(r, 0, 255), _clamp(g, 0, 255), _clamp(b, 0, 255), 0, 0, 0, 0, 0, lo, hi]
    )


def build_segment_brightness(segments: Iterable[int], pct: int) -> bytes:
    mask = segments_to_mask(segments)
    lo, hi = mask & 0xFF, (mask >> 8) & 0xFF
    return build_packet(0x33, 0x05, [0x15, 0x02, _clamp(pct, 0, 100), lo, hi])


def build_segment_paint(groups: Iterable[SegmentColorGroup]) -> list[bytes]:
    """One packet per (segments, colour) group; distinct colours require distinct packets."""
    return [build_segment_color(segments, r, g, b) for segments, (r, g, b) in groups]


def build_color_rgb(r: int, g: int, b: int) -> bytes:
    return build_segment_color(ALL_SEGMENTS, r, g, b)


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
    k = _clamp(kelvin, 2000, 9000)
    r, g, b = kelvin_to_rgb(k)
    # App form: 33 05 15 01 00 00 00 <Khi Klo> <R G B> ... FF 7F (kelvin true-white; RGB is a preview)
    return build_packet(0x33, 0x05, [0x15, 0x01, 0, 0, 0, (k >> 8) & 0xFF, k & 0xFF, r, g, b, 0xFF, 0x7F])


def build_white_brightness(percent: int) -> bytes:
    # Whole-strip brightness: per-segment brightness command with the all-segments mask (0x7fff)
    return build_segment_brightness(ALL_SEGMENTS, percent)


def build_scene(scene_id: int) -> bytes:
    # Scene id is a fixed 2-byte little-endian field (validated live).
    return build_packet(0x33, 0x05, [0x04, *scene_id.to_bytes(2, "little")])


def _a3_frame(index: int, chunk: bytes) -> bytes:
    packet = bytearray([MULTI_PACKET_PREFIX, index, *chunk])
    packet = (packet + bytearray(19 - len(packet)))[:19]
    packet.append(xor_checksum(packet))
    return bytes(packet)


def build_a3_multi(type_byte: int, body: bytes, *, terminator: bool = False) -> list[bytes]:
    """Fragment a body into 0xA3 multi-frames (H617A §6).

    Frames ``[0x01, chunk_count, type_byte, *body]`` into 17-byte chunks, each emitted as a
    20-byte ``0xA3 <index|0xFF>`` frame with an XOR checksum. Shared by scenes, music params and
    custom effects so there is a single fragmenter and a single XOR path. With ``terminator`` the
    data chunks keep sequential indices and an extra empty ``0xFF`` frame closes the sequence, the
    form the Govee app uses for Finger Sketch (``TYPE 0x03``).
    """
    data = bytes([type_byte]) + body
    chunk_count = math.ceil((len(data) + 2) / 17)
    payload = bytes([0x01, chunk_count + (1 if terminator else 0)]) + data
    chunks = [payload[index : index + 17] for index in range(0, len(payload), 17)]
    last = len(chunks) - 1
    packets = [_a3_frame(index if terminator or index != last else 0xFF, chunk) for index, chunk in enumerate(chunks)]
    if terminator:
        packets.append(_a3_frame(0xFF, b""))
    return packets


def build_scene_multi(scene_param_b64: str, scene_code: int, scene_type: int = 2) -> list[bytes]:
    if not scene_param_b64:
        return [build_scene(scene_code)]
    return [*build_a3_multi(scene_type, base64.b64decode(scene_param_b64)), build_scene(scene_code)]


def build_h6199_scene(scene_param_b64: str, scene_code: int, scene_type: int = 2) -> list[bytes]:
    """Build the H6199 scene body and its model-specific three-byte activation."""
    activation_type = scene_type if scene_param_b64 else 0x01
    activation = build_packet(0x33, 0x05, [0x04, *scene_code.to_bytes(2, "little"), activation_type])
    if not scene_param_b64:
        return [activation]
    return [*build_a3_multi(scene_type, base64.b64decode(scene_param_b64)), activation]


# --- Custom-effect content encoders (§3.3) -----------------------------------------------------
# Every builder returns list[bytes]; the store/entity layers never see raw bytes. Tier-1 segments
# reuse the live write-path. Combo is directly validated; the remaining Tier-2 DIY/Vibrant
# encoders stay capture-pinned and experimental. Packet bytes live only here.


def build_diy_activate(slot: int, type_byte: int | None = None) -> bytes:
    """DIY/Vibrant activation ``33 05 0a <slot> [type]`` (H617A §3 "DIY select"); ``slot`` is app-assigned.

    Finger Sketch appends its ``TYPE 0x03`` after the slot; the other DIY kinds omit it.
    """
    params = [COLOR_MODE_DIY, slot]
    if type_byte is not None:
        params.append(type_byte)
    return build_packet(0x33, 0x05, params)


def _group_indices[T](values: Iterable[T | None], *, start: int) -> list[tuple[T, list[int]]]:
    """Group non-``None`` values to their ``start``-based indices, preserving first-seen order."""
    grouped: dict[T, list[int]] = {}
    order: list[T] = []
    for index, value in enumerate(values, start=start):
        if value is None:
            continue
        if value not in grouped:
            grouped[value] = []
            order.append(value)
        grouped[value].append(index)
    return [(value, grouped[value]) for value in order]


def _group_by_colour(colors: Iterable[RGB | None]) -> list[tuple[RGB, list[int]]]:
    return _group_indices(colors, start=1)  # write-path segment indices are 1-based


def _group_by_level(levels: Iterable[int | None]) -> list[tuple[int, list[int]]]:
    return _group_indices(levels, start=1)


def _group_by_colour_0based(colors: Iterable[RGB | None]) -> list[tuple[RGB, list[int]]]:
    return _group_indices(colors, start=0)  # Finger Sketch segment indices are 0-based


def build_segment_content(content: SegmentContent, *, segment_count: int) -> list[bytes]:
    """Static per-segment paint via the live write-path (Tier 1). ``colors[i]`` targets segment ``i+1``."""
    packets = [build_segment_color(indices, *rgb) for rgb, indices in _group_by_colour(content.colors)]
    if content.brightness:
        packets += [build_segment_brightness(indices, pct) for pct, indices in _group_by_level(content.brightness)]
    return packets


def build_sketch(content: SketchContent, *, segment_count: int) -> list[bytes]:
    # VALIDATED: Finger Sketch live H617A 3.02.24 (2026-07-16); body + 2-frame A3 + 33 05 0a 20 03.
    body = bytes([content.motion, content.speed, content.brightness, *content.background])
    groups = _group_by_colour_0based(content.colors)
    body += bytes([len(groups)])
    for rgb, indices in groups:
        body += bytes([len(indices), *rgb, *indices])
    return [*build_a3_multi(0x03, body, terminator=True), build_diy_activate(SKETCH_DIY_SLOT, 0x03)]


_VIBRANT_GAMMA = 2.2  # Vibrant interpolates each channel in gamma-2.2 linear light (measured 2026-07-20)


def _interpolate(stops: tuple[RGB, ...], n: int, *, gamma: float | None = None) -> list[RGB]:
    """RGB gradient of ``stops`` across ``n`` segments (endpoints inclusive).

    Linear in sRGB by default; pass ``gamma`` (Vibrant uses ``2.2``) to interpolate in linear
    light, which is what the app writes on the wire.
    """
    if n <= 0:
        return []
    if n == 1 or len(stops) == 1:
        return [stops[0]] * n
    exponent = gamma if gamma is not None else 1.0

    def _mix(a: int, b: int, fraction: float) -> int:
        lower, upper = math.pow(a / 255, exponent), math.pow(b / 255, exponent)
        return round(math.pow(lower + (upper - lower) * fraction, 1 / exponent) * 255)

    span = len(stops) - 1
    result: list[RGB] = []
    for index in range(n):
        position = index * span / (n - 1)
        lower = min(int(position), span - 1)
        fraction = position - lower
        start_rgb, end_rgb = stops[lower], stops[lower + 1]
        channels = [_mix(a, b, fraction) for a, b in zip(start_rgb, end_rgb, strict=True)]
        result.append((channels[0], channels[1], channels[2]))
    return result


def build_vibrant(content: VibrantContent, *, segment_count: int) -> list[bytes]:
    # VALIDATED: Vibrant live H617A 3.02.24 (2026-07-20); TYPE 0x03 gradient body + 33 05 0a 84 03.
    seg_rgb = _interpolate(content.stops, segment_count, gamma=_VIBRANT_GAMMA)
    body = bytes([0x09, 0x00, 0x64, 0x01, 0x01, 0x01])  # motion Clockwise, speed 0, brightness 100, bg (1,1,1)
    groups = _group_by_colour_0based(seg_rgb)
    body += bytes([len(groups)])
    for rgb, indices in groups:
        body += bytes([len(indices), *rgb, *indices])
    return [*build_a3_multi(0x03, body), build_diy_activate(VIBRANT_DIY_SLOT, 0x03)]


def build_flat_diy(content: FlatContent) -> list[bytes]:
    # EXPERIMENTAL: harness=diy-flat encoding=capture-pinned
    palette = b"".join(bytes(colour) for colour in content.palette)
    body = bytes([content.family, content.variant, content.speed, len(palette)]) + palette
    return [*build_a3_multi(0x04, body), build_diy_activate(DEFAULT_DIY_SLOT)]


def build_combo(content: ComboContent, *, slot: int = DEFAULT_DIY_SLOT) -> list[bytes]:
    palette = b"".join(bytes(colour) for colour in content.palette)
    sequence = b"".join(bytes([family, variant]) for family, variant in content.effects)
    body = bytes([0xFF, content.variant, content.speed, len(palette)]) + palette + bytes([len(sequence)]) + sequence
    return [*build_a3_multi(0x04, body), build_diy_activate(slot)]


def build_custom_effect(content: EffectContent, *, segment_count: int) -> list[bytes]:
    """Route a content object to its per-kind encoder; ``UnknownContent`` is never applyable (#7a)."""
    match content:
        case SegmentContent():
            return build_segment_content(content, segment_count=segment_count)
        case SketchContent():
            return build_sketch(content, segment_count=segment_count)
        case VibrantContent():
            return build_vibrant(content, segment_count=segment_count)
        case FlatContent():
            return build_flat_diy(content)
        case ComboContent():
            return build_combo(content)
        case _:  # UnknownContent (or any future unhandled kind): preserved on load, never applyable (#7a)
            raise EffectValidationError("unknown_kind_not_applyable")


STATE_QUERY = build_packet(STATUS_HEADER, POWER_PACKET_TYPE, [])
BRIGHTNESS_QUERY = build_packet(STATUS_HEADER, BRIGHTNESS_PACKET_TYPE, [])
COLOR_MODE_QUERY = build_packet(STATUS_HEADER, COLOR_PACKET_TYPE, [])
FW_QUERY = build_packet(STATUS_HEADER, FIRMWARE_PACKET_TYPE, [])
HW_QUERY = build_packet(STATUS_HEADER, HARDWARE_PACKET_TYPE, [0x03])
KEEP_ALIVE = STATE_QUERY


def build_video_mode(
    full_screen: bool = True,
    game_mode: bool = False,
    saturation: int = 100,
    sound_effects: bool = False,
    sound_effects_softness: int = 100,
) -> bytes:
    # H6199 video frame; region 1=all/0=part. iOS always sends the full frame: sound flag plus a
    # softness byte (floor 0x01) that persists even when sound is off.
    params = [
        COLOR_MODE_VIDEO,
        int(full_screen),
        int(game_mode),
        _clamp(saturation, 0, 100),
        int(sound_effects),
        _clamp(sound_effects_softness, 1, 100),
    ]
    return build_packet(0x33, 0x05, params)


def build_video_white_balance(red: int, blue: int) -> bytes:
    """Build the H6199 raw two-axis DreamView white-balance frame."""
    return build_packet(0x33, 0xA9, [0x00, 0x03, 0x01, _clamp(red, 0, 255), _clamp(blue, 0, 255)])


def build_music_mode_with_color(
    mode_id: int,
    sensitivity: int = 99,
    color: tuple[int, int, int] | None = None,
    calm: bool = False,
) -> bytes:
    # byte 5 STYLE = Dynamic(0)/Calm(1); byte 6 COUNT = manual colour count (0 = auto-colour on).
    params = [0x13, mode_id, _clamp(sensitivity, 0, 99), int(calm)]
    if color is not None:
        params.extend([0x01, *(_clamp(channel, 0, 255) for channel in color)])
    return build_packet(0x33, 0x05, params)


# --- Music per-mode movement parameters (§2.3, EXPERIMENTAL, capture-pinned) -------------------
# H617A movement params ride the MultipleController4Music command 0x41 body, fragmented over a3
# (H617A §6, docs/ble-protocol-h617a.md lines 217-234). Assembled body =
# `01 <fragCount> 41 <MODE> <count> <RGB x count> <mode-specific tail>`; a3 offsets are absolute
# from the assembled byte 0, so the body-local index is `offset - 3`. Every template byte below is
# replayed byte-exact from the 2026-07-09 validation run and current iOS 7.5.21 captures. Volatile
# animation bytes (Separation[22], Piano[30]) are never synthesised. Locked by byte-exact A/B/A
# decode tests in tests/test_protocol.py.
_MUSIC_PARAM_TEMPLATE: dict[int, bytes] = {
    # Bloom 0x30: current iOS Dynamic baseline; [27]=style companion (Dynamic 0x50 / Calm 0x14).
    0x30: bytes.fromhex("3007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000"),
    # Shiny 0x31: current iOS Dynamic baseline; [20:22]=style companion (05 64 / 14 46).
    0x31: bytes.fromhex("3105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000"),
    # Separation 0x32: report step music-p-gradient (= pcap idx5); [20]=seppoint 1, [21]=gradient on.
    0x32: bytes.fromhex("3205ff7f00ff0000ffff000000ff00ff0001015e0000000000000000000000"),
    # Hopping 0x33 (3-frag): report step music-p-relbright (= pcap idx16); [29]=relative brightness 50.
    0x33: bytes.fromhex(
        "3307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
    ),
    # Piano Keys 0x34: report step music-p-keys (= pcap idx20); [27]=key count 15, [30]=volatile.
    0x34: bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
    # Fountain 0x35: current iOS Clockwise baseline; direction is the pair [26,28].
    0x35: bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0001055000000000"),
    # Day & Night 0x37: pcap baseline idx27/29; [26]=segments 1, [27]=speed 10 (reproduces both A/B frames).
    0x37: bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
}
# mode -> captured palette colour count (body-local byte 1); guards palette overrides so the
# `<RGB x count>` region can never shift the downstream param offsets.
_MUSIC_PARAM_COUNT: dict[int, int] = {mode: body[1] for mode, body in _MUSIC_PARAM_TEMPLATE.items()}
# Absolute a3 offsets that carry volatile animation state: replayed verbatim, never written (VAL "CAVEAT").
_VOLATILE_OFFSETS: dict[int, frozenset[int]] = {
    0x32: frozenset({22}),
    0x34: frozenset({30}),
}
_MUSIC_PARAM_BASE = 3  # assembled-body base: template byte 0 is the MODE byte at assembled index 3.


def build_music_params_a3(
    mode: int,
    overrides: dict[int, int],
    palette: list[tuple[int, int, int]] | None = None,
) -> list[bytes]:
    """Build the H617A per-mode music movement frame (command 0x41, fragmented over a3).

    Replays the capture-pinned template for ``mode`` verbatim, overlaying only the decoded param
    offsets in ``overrides`` (a3-absolute). Volatile animation bytes are never written, and a
    palette whose length differs from the captured count is rejected so the ``<RGB x count>`` region
    cannot shift the downstream offsets.
    """
    # EXPERIMENTAL: harness=music-params encoding=capture-pinned
    # source: validate-20260709-122350.pcap + validation-report-20260709-123428.json; layout H617A §3.
    body = bytearray(_MUSIC_PARAM_TEMPLATE[mode])
    if palette is not None:
        if len(palette) != _MUSIC_PARAM_COUNT[mode]:
            raise EffectValidationError("palette_count_mismatch")
        body[2 : 2 + 3 * len(palette)] = bytes(channel for rgb in palette for channel in rgb)
    volatile = _VOLATILE_OFFSETS.get(mode, frozenset())
    for offset, value in overrides.items():
        if offset in volatile:
            raise ValueError("volatile byte; never write")
        body[offset - _MUSIC_PARAM_BASE] = _clamp(value, 0, 255)
    return build_a3_multi(0x41, bytes(body))


class ParsedMode(Enum):
    """Operating mode from a colour-mode reply; DIY carries a slot, music and video their own state."""

    UNKNOWN = auto()
    COLOUR = auto()
    SCENE = auto()
    DIY = auto()
    MUSIC = auto()
    VIDEO = auto()


@dataclass(frozen=True)
class ParsedColorModeResponse:
    mode: ParsedMode = ParsedMode.UNKNOWN
    effect: str | None = None
    diy_slot: int | None = None
    music_mode: str | None = None
    video_mode: str | None = None
    video_full_screen: bool | None = None
    video_saturation: int | None = None
    video_sound_effects: bool | None = None
    video_sound_effects_softness: int | None = None
    music_sensitivity: int | None = None
    music_calm: bool | None = None
    music_color: tuple[int, int, int] | None = None
    rgb_color: tuple[int, int, int] | None = None
    white_brightness: int | None = None


def parse_color_mode_response(payload: bytes) -> ParsedColorModeResponse:
    if not payload:
        raise ValueError("Color mode payload is empty")
    mode = payload[0]
    if mode == COLOR_MODE_SCENE:
        scene_bytes = payload[1:] or b"\x00"
        while len(scene_bytes) > 1 and scene_bytes[-1] == 0:
            scene_bytes = scene_bytes[:-1]
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE, effect=SCENE_EFFECT_BY_ID.get(int.from_bytes(scene_bytes, "little"))
        )
    if mode == COLOR_MODE_DIY:
        return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_slot=_get(payload, 1))
    if mode == COLOR_MODE_VIDEO:
        return ParsedColorModeResponse(
            mode=ParsedMode.VIDEO,
            video_mode="game" if bool(_get(payload, 2)) else "movie",
            video_full_screen=bool(v) if (v := _get(payload, 1)) is not None else None,
            video_saturation=_get(payload, 3),
            video_sound_effects=bool(v) if (v := _get(payload, 4)) is not None else None,
            video_sound_effects_softness=_get(payload, 5),
        )
    if mode == COLOR_MODE_MUSIC:
        mode_id = _get(payload, 1)
        style = _get(payload, 3)
        color_parts = (_get(payload, 5), _get(payload, 6), _get(payload, 7))
        music_color = (
            cast(tuple[int, int, int], color_parts) if _get(payload, 4) == 0x01 and None not in color_parts else None
        )
        # byte5 (index 3) is Dynamic/Calm only for Rhythm; other modes repurpose it, so leave calm unset.
        music_calm = bool(style) if mode_id == RHYTHM_MODE_ID and style is not None else None
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=MUSIC_SLUG_BY_ID.get(mode_id or -1),
            music_sensitivity=_get(payload, 2),
            music_calm=music_calm,
            music_color=music_color,
        )
    if mode != COLOR_MODE_STATIC:
        return ParsedColorModeResponse(mode=ParsedMode.UNKNOWN)
    rgb_parts = (_get(payload, 2), _get(payload, 3), _get(payload, 4))
    rgb_color = cast(tuple[int, int, int], rgb_parts) if _get(payload, 1) == 0x01 and None not in rgb_parts else None
    return ParsedColorModeResponse(
        mode=ParsedMode.COLOUR,
        rgb_color=rgb_color,
        white_brightness=(
            _clamp(v, 0, 100) if _get(payload, 1) == 0x02 and (v := _get(payload, 2)) is not None else None
        ),
    )


def _decode_version(payload: bytes) -> str | None:
    """Decode an ASCII version string from a status payload, trimming NUL padding."""
    text = payload.split(b"\x00", 1)[0].decode("ascii", "ignore").strip()
    return text or None


def parse_fw_version(payload: bytes) -> str | None:
    """Decode the firmware version from an ``aa 06`` reply payload (e.g. ``"3.02.24"``)."""
    return _decode_version(payload)


def parse_hw_version(payload: bytes) -> str | None:
    """Decode the hardware version from an ``aa 07 03`` reply payload."""
    if not payload or payload[0] != 0x03:
        return None
    return _decode_version(payload[1:])


# Experimental timer & power-off encoders (decode-only; see plan-research-encodings.md §2-3).


class Weekday(IntEnum):
    """Timer repeat-mask bit positions (Mon=bit0 .. Sun=bit6)."""

    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6


TIMER_REPEAT_ONCE = 0x80  # high bit set with no weekday bits -> fires once


def timer_repeat(days: Iterable[Weekday] = ()) -> int:
    """Encode weekdays as a timer repeat byte (Mon=bit0 .. Sun=bit6).

    Empty yields 0x80 (fires once); every weekday selected yields 0x00 (every day, as the app
    sends it); any other subset is 0x80 | mask.
    """
    mask = 0
    for day in days:
        if not 0 <= int(day) <= 6:
            raise ValueError(f"weekday {day!r} out of range 0..6")
        mask |= 1 << int(day)
    if mask == 0x7F:
        return 0x00
    return TIMER_REPEAT_ONCE | mask


def parse_timer_repeat(repeat: int) -> frozenset[Weekday]:
    """Decode a timer repeat byte to its weekday set (empty = one-time, all seven = every day)."""
    if (repeat & TIMER_REPEAT_ONCE) == 0:
        return frozenset(Weekday)
    return frozenset(day for day in Weekday if repeat & (1 << int(day)))


def build_timer_schedule(
    index: int,
    enabled: bool,
    on_action: bool,
    hour: int,
    minute: int,
    repeat_days: Iterable[Weekday] = (),
) -> bytes:
    """Build a scheduled on/off timer slot (0x23); repeat_days empty = fire once."""
    # EXPERIMENTAL: harness=G encoding=decode-only
    if not 0 <= index <= 3:
        raise ValueError(f"timer slot {index} out of range 0..3")
    enable_and_type = (0x80 if enabled else 0x00) | (0x01 if on_action else 0x00)
    params = [index, enable_and_type, _clamp(hour, 0, 23), _clamp(minute, 0, 59), timer_repeat(repeat_days)]
    return build_packet(0x33, 0x23, params)


def build_timer_sleep(enabled: bool, start_brightness: int, close_minutes: int, current_minutes: int = 0) -> bytes:
    """Build a sleep/fade-off timer (0x11): fade from start_brightness over close_minutes."""
    # EXPERIMENTAL: harness=G encoding=decode-only
    params = [
        int(enabled),
        _clamp(start_brightness, 10, 100),
        _clamp(close_minutes, 0, 255),
        _clamp(current_minutes, 0, 255),
    ]
    return build_packet(0x33, 0x11, params)


def build_timer_wakeup(
    enabled: bool,
    end_brightness: int,
    hour: int,
    minute: int,
    repeat_days: Iterable[Weekday] = (),
    duration_minutes: int = 10,
) -> bytes:
    """Build a wake-up/sunrise timer (0x12): ramp to end_brightness over duration_minutes."""
    # EXPERIMENTAL: harness=G encoding=decode-only
    params = [
        int(enabled),
        _clamp(end_brightness, 10, 100),
        _clamp(hour, 0, 23),
        _clamp(minute, 0, 59),
        timer_repeat(repeat_days),
        _clamp(duration_minutes, 10, 60),
    ]
    return build_packet(0x33, 0x12, params)


def build_poweroff_memory(enabled: bool) -> bytes:
    """Build a power-off memory toggle (0x41): restore last state after power loss."""
    # EXPERIMENTAL: harness=TBD encoding=decode-only
    return build_packet(0x33, 0x41, [int(enabled)])


@dataclass(frozen=True)
class ParsedTimerSchedule:
    enabled: bool
    on_action: bool
    hour: int
    minute: int
    repeat_days: frozenset[Weekday]


@dataclass(frozen=True)
class ParsedSleepTimer:
    enabled: bool
    start_brightness: int
    close_minutes: int
    current_minutes: int


@dataclass(frozen=True)
class ParsedWakeUpTimer:
    enabled: bool
    end_brightness: int
    hour: int
    minute: int
    repeat_days: frozenset[Weekday]
    duration_minutes: int


@dataclass(frozen=True)
class ParsedPowerOffMemory:
    enabled: bool
    mode: int | None = None


def parse_timer_schedule(payload: bytes) -> ParsedTimerSchedule:
    """Decode one scheduled-timer slot record [enableAndType, hh, mm, repeat]."""
    # Slot record layout confirmed live 2026-07-09 (weekday bits Mon=bit0..Sun=bit6).
    if len(payload) < 4:
        raise ValueError("scheduled timer payload too short")
    enable_and_type = payload[0]
    return ParsedTimerSchedule(
        enabled=bool(enable_and_type & 0x80),
        on_action=bool(enable_and_type & 0x01),
        hour=payload[1],
        minute=payload[2],
        repeat_days=parse_timer_repeat(payload[3]),
    )


def parse_timer_schedule_table(payload: bytes) -> list[ParsedTimerSchedule]:
    """Decode the full aa 23 reply (0xff prefix + four 4-byte slot records) into per-slot timers."""
    body = payload[1:] if payload[:1] == b"\xff" else payload
    return [parse_timer_schedule(body[i : i + 4]) for i in range(0, len(body) - 3, 4)]


def parse_timer_sleep(payload: bytes) -> ParsedSleepTimer:
    """Decode a sleep-timer aa 11 reply [enable, startBri, closeMin, curMin]."""
    # EXPERIMENTAL: harness=G encoding=decode-only
    if len(payload) < 3:
        raise ValueError("sleep timer payload too short")
    return ParsedSleepTimer(
        enabled=bool(payload[0]),
        start_brightness=payload[1],
        close_minutes=payload[2],
        current_minutes=payload[3] if len(payload) > 3 else 0,
    )


def parse_timer_wakeup(payload: bytes) -> ParsedWakeUpTimer:
    """Decode a wake-up aa 12 reply [enable, endBri, hh, mm, repeat, duration]."""
    # EXPERIMENTAL: harness=G encoding=decode-only
    if len(payload) < 6:
        raise ValueError("wake-up timer payload too short")
    return ParsedWakeUpTimer(
        enabled=bool(payload[0]),
        end_brightness=payload[1],
        hour=payload[2],
        minute=payload[3],
        repeat_days=parse_timer_repeat(payload[4]),
        duration_minutes=payload[5],
    )


def parse_poweroff_memory(payload: bytes) -> ParsedPowerOffMemory:
    """Decode a power-off memory aa 41 reply [enabled, mode]."""
    # EXPERIMENTAL: harness=TBD encoding=decode-only
    if not payload:
        raise ValueError("power-off memory payload is empty")
    return ParsedPowerOffMemory(enabled=bool(payload[0]), mode=_get(payload, 1))


# Builder -> protocol-evidence registry. Every public builder/parser (and the query constants)
# cites the in-repo evidence proving its byte layout, plus a status:
#   VALIDATED    - byte layout confirmed by a live/on-wire capture; ships on the normal surface.
#   EXPERIMENTAL - unvalidated (no live capture), capture-pending, or a deliberately gated Tier-2 feature; the
#                  builder also carries a "# EXPERIMENTAL: harness=<id> encoding=<..>" source marker.
# Shorthand: H617A/H6199 = docs/ble-protocol-*.md; MEM = docs/device-memory-and-sharing.md.
# tests/test_protocol_traceability.py keeps this registry in lockstep with the builder surface,
# the source markers, and the byte-exact tests, so nothing ships un-traced.
@dataclass(frozen=True)
class Evidence:
    """Where a builder's byte layout is proven, and whether it is VALIDATED or EXPERIMENTAL."""

    status: str
    source: str


BUILDER_EVIDENCE: dict[str, Evidence] = {
    "build_packet": Evidence("VALIDATED", "H617A §2 framing: 20-byte frame + XOR at byte[19]"),
    "build_power": Evidence("VALIDATED", "H617A §3/§7 power 33 01; live byte-identical"),
    "build_brightness": Evidence("VALIDATED", "H617A §3/§7 brightness 33 04; live, 1:1 linear"),
    "build_segment_color": Evidence("VALIDATED", "H617A §3 colour 33 05 15 01, mask[12:14]; live"),
    "build_segment_brightness": Evidence("VALIDATED", "H617A §3/§7 seg brightness 33 05 15 02, mask[5:7]; live"),
    "build_segment_paint": Evidence("VALIDATED", "H617A §5 one 33 05 15 01 frame per colour group; live"),
    "build_color_rgb": Evidence("VALIDATED", "H617A §3/§5 whole-strip colour, mask 0x7FFF; live"),
    "build_color_temp": Evidence(
        "VALIDATED", "H617A §3 colour-temp 33 05 15 01 00 00 00 <K>; live 2-9kK on H617A; H6199 parity unattributed"
    ),
    "build_white_brightness": Evidence(
        "VALIDATED", "H617A §7 white brightness 33 05 15 02, mask 0x7FFF; live on H617A; H6199 reuse unattributed"
    ),
    "build_scene": Evidence("VALIDATED", "H617A §3/§6 scene 33 05 04 <code_LE>; Sunrise/Rainbow live 2026-07-16"),
    "build_a3_multi": Evidence("VALIDATED", "H617A §6 0xA3 multi-frame fragmenter; XOR at byte[19]; live"),
    "build_scene_multi": Evidence(
        "VALIDATED", "H617A §6 0xA3 body TYPE 0x01/0x02 + 33 05 04 activate; Aurora/Halloween byte-exact 2026-07-16"
    ),
    "build_h6199_scene": Evidence(
        "VALIDATED", "H6199 simple type-01 and A3 type-02 scene activations; iOS app-sniff 2026-07-12"
    ),
    "build_diy_activate": Evidence(
        "VALIDATED", "H617A §3 DIY select 33 05 0a <slot>; slot F0 accepted and read back live 2026-07-15"
    ),
    "build_segment_content": Evidence(
        "VALIDATED", "H617A §3/§7 seg colour+brightness reuse; VAL single/all/one-seg live"
    ),
    "build_sketch": Evidence(
        "VALIDATED", "H617A §2.4 Finger Sketch TYPE 0x03; body/framing/activation live 2026-07-16"
    ),
    "build_vibrant": Evidence("VALIDATED", "Live H617A 2026-07-20; TYPE 0x03 gamma-2.2 gradient, 33 05 0a 84 03"),
    "build_flat_diy": Evidence("EXPERIMENTAL", "CAT §2.2 flat DIY TYPE 0x04; capture-pinned, gated Tier-2"),
    "build_combo": Evidence(
        "VALIDATED",
        "H617A §6 Combo TYPE 04 FAMILY FF; current iOS body plus slot F0 direct write/read-back 2026-07-15",
    ),
    "build_custom_effect": Evidence("VALIDATED", "dispatcher over per-kind encoders (own evidence); Unknown rejected"),
    "build_music_mode_with_color": Evidence(
        "VALIDATED",
        "H617A music 33 05 13 <mode><sens><style><count>; STYLE byte5 Dynamic(0)/Calm(1), COUNT byte6 "
        "= manual colour count (0=auto-colour on)+RGB; 11 modes live-confirmed",
    ),
    "build_music_params_a3": Evidence(
        "EXPERIMENTAL", "VAL a3 music body H617A §3 (lines 217-234); capture-pinned, volatile bytes replayed"
    ),
    "build_video_mode": Evidence(
        "VALIDATED",
        "H6199 33 05 00 region/mode/sat/sound/softness; always-full frame, softness persists (floor 0x01) "
        "when sound off; app-sniff 2026-07-12 + h6199-video-controls-batch.pcap",
    ),
    "build_video_white_balance": Evidence(
        "VALIDATED",
        "H6199 33 a9 00 03 01 <red><blue>; independent raw axes app-sniffed 2026-07-12; UI mapping unproven",
    ),
    "build_timer_schedule": Evidence("EXPERIMENTAL", "H617A §4 timer 33 23; write live, ships gated Tier-2"),
    "build_timer_sleep": Evidence("EXPERIMENTAL", "H617A §4 sleep 33 11; reply captured (OBSERVE)"),
    "build_timer_wakeup": Evidence("EXPERIMENTAL", "H617A §4 wake-up 33 12; reply captured (OBSERVE)"),
    "build_poweroff_memory": Evidence("EXPERIMENTAL", "MEM §1 power-off memory 33 41; no live capture"),
    "split_status_frame": Evidence("VALIDATED", "H617A §4 status aa <type>; 20-byte XOR split; live"),
    "parse_color_mode_response": Evidence(
        "VALIDATED", "H617A §4 colour-mode aa 05 (15/04/0a/00/13); DIY slot F0 read back live 2026-07-15"
    ),
    "parse_fw_version": Evidence("VALIDATED", "H617A §4 firmware aa 06 -> ASCII '3.02.24'; VAL live capture"),
    "parse_hw_version": Evidence(
        "VALIDATED", "H617A/H6199 aa 07 03 -> ASCII hardware version; iOS app-sniff 2026-07-12"
    ),
    "parse_timer_repeat": Evidence("VALIDATED", "H617A §4 repeat byte Mon=bit0..Sun=bit6; live"),
    "parse_timer_schedule": Evidence("VALIDATED", "H617A §4 slot [enableAndType,hh,mm,repeat]; live"),
    "parse_timer_schedule_table": Evidence("VALIDATED", "H617A §4/§7 aa 23 ff + four 4-byte slots; live"),
    "parse_timer_sleep": Evidence("EXPERIMENTAL", "H617A §4 aa 11 sleep reply; OBSERVE"),
    "parse_timer_wakeup": Evidence("EXPERIMENTAL", "H617A §4 aa 12 wake reply; OBSERVE"),
    "parse_poweroff_memory": Evidence("EXPERIMENTAL", "MEM §1 aa 41 reply [enabled,mode]; no live capture"),
    "STATE_QUERY": Evidence("VALIDATED", "H617A §4 power query aa 01; live keep-alive"),
    "BRIGHTNESS_QUERY": Evidence("VALIDATED", "H617A §4 brightness query aa 04; mirrors 33 04"),
    "COLOR_MODE_QUERY": Evidence("VALIDATED", "H617A §4 colour-mode query aa 05; live"),
    "FW_QUERY": Evidence("VALIDATED", "H617A §4 firmware query aa 06; VAL connect handshake"),
    "HW_QUERY": Evidence(
        "VALIDATED", "H617A/H6199 hardware query aa 07 03; replies 3.01.01/3.02.01 app-sniffed 2026-07-12"
    ),
    "KEEP_ALIVE": Evidence("VALIDATED", "H617A §4 aa 01 ~2s keep-alive (= STATE_QUERY)"),
}
