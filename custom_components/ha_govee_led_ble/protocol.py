"""Govee BLE protocol — 20-byte packets with XOR checksum at byte 19."""

import base64
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

from .const import MUSIC_MODE_SLUGS
from .generated_protocol_adapter import (
    build_brightness as _build_generated_brightness,
)
from .generated_protocol_adapter import build_brightness_query as _build_generated_brightness_query
from .generated_protocol_adapter import build_colour_mode_query as _build_generated_colour_mode_query
from .generated_protocol_adapter import (
    build_colour_temperature as _build_generated_colour_temperature,
)
from .generated_protocol_adapter import build_firmware_query as _build_generated_firmware_query
from .generated_protocol_adapter import (
    build_h617a_scene as _build_generated_h617a_scene,
)
from .generated_protocol_adapter import (
    build_h6199_blank_screen as _build_generated_blank_screen,
)
from .generated_protocol_adapter import (
    build_h6199_blank_screen_query as _build_generated_blank_screen_query,
)
from .generated_protocol_adapter import (
    build_h6199_relative_brightness as _build_generated_relative_brightness,
)
from .generated_protocol_adapter import (
    build_h6199_relative_brightness_query as _build_generated_relative_brightness_query,
)
from .generated_protocol_adapter import (
    build_h6199_scene as _build_generated_h6199_scene,
)
from .generated_protocol_adapter import (
    build_h6199_video as _build_generated_video,
)
from .generated_protocol_adapter import (
    build_h6199_white_balance as _build_generated_white_balance,
)
from .generated_protocol_adapter import (
    build_h6199_white_balance_query as _build_generated_white_balance_query,
)
from .generated_protocol_adapter import build_hardware_query as _build_generated_hardware_query
from .generated_protocol_adapter import build_music_mode as _build_generated_music
from .generated_protocol_adapter import build_power as _build_generated_power
from .generated_protocol_adapter import build_power_query as _build_generated_power_query
from .generated_protocol_adapter import (
    build_segment_brightness as _build_generated_segment_brightness,
)
from .generated_protocol_adapter import (
    build_segment_colour as _build_generated_segment_colour,
)
from .generated_protocol_adapter import parse_command as _parse_generated_command
from .generated_protocol_adapter import parse_status as _parse_generated_status
from .generated_protocol_adapter import xor_checksum
from .scenes import MODEL_SCENES, SCENES, SceneSpeed

WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b11"
READ_UUID = "00010203-0405-0607-0809-0a0b0c0d2b10"


COMMAND_HEADER = 0x33
STATUS_HEADER = 0xAA
POWER_PACKET_TYPE = 0x01
BRIGHTNESS_PACKET_TYPE = 0x04
COLOR_PACKET_TYPE = 0x05
FIRMWARE_PACKET_TYPE = 0x06
HARDWARE_PACKET_TYPE = 0x07
# H6199 registers reached from the vendor app's video sheet (h6199_command_write::command_op).
DISPLAY_SETTING_PACKET_TYPE = 0xA9
RELATIVE_BRIGHTNESS_PACKET_TYPE = 0xAE
RELATIVE_BRIGHTNESS_EDGES = 4
RELATIVE_BRIGHTNESS_HEAD = 0x01
# Which setting a 33 a9 write addresses (h6199_command_write::display_setting).
DISPLAY_SETTING_WHITE_BALANCE = 0x00
DISPLAY_SETTING_BLANK_SCREEN = 0x0A
COLOR_MODE_SCENE = 0x04
COLOR_MODE_VIDEO = 0x00
COLOR_MODE_MUSIC = 0x13
COLOR_MODE_STATIC = 0x15
COLOR_MODE_DIY = 0x0A
# Sub-selectors inside a 33 05 15 write (command_write::static_color / static_brightness). They
# exist on the write side only: the aa 05 15 read-back does not echo them (status_reply::cm_static).
STATIC_SUB_COLOR = 0x01
STATIC_SUB_BRIGHTNESS = 0x02
MUSIC_SLUG_BY_ID: dict[int, str] = {code: slug for slug, code in MUSIC_MODE_SLUGS.items()}
RHYTHM_MODE_ID = MUSIC_MODE_SLUGS["rhythm"]
SCENE_EFFECT_BY_ID: dict[int, str] = {scene.code: name for name, scene in SCENES.items()}
SCENE_EFFECT_BY_MODEL_ID: dict[str, dict[int, str]] = {
    model: {scene.code: name for name, scene in scenes.items()} for model, scenes in MODEL_SCENES.items()
}
MULTI_PACKET_PREFIX = 0xA3
# Scene Speed field locations are owned by govee_common::effect_layer.
MOVE_IN_OFFSET = -5
MOVE_ALL_OFFSET = -2
_SCENE_BRIGHTNESS_BLOCK_COUNT_OFFSET = 5
_SCENE_FIRST_BRIGHTNESS_SPEED_OFFSET = 9
_SCENE_BRIGHTNESS_BLOCK_SIZE = 6
_SCENE_COLOUR_SPEED_BASE_OFFSET = 7


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True, slots=True)
class ParsedStatusEnvelope:
    domain: int
    payload: bytes
    generated: Any


def decode_status_frame(
    frame: bytes,
    model: str = "H617A",
) -> ParsedStatusEnvelope | None:
    """Parse one fixed-size status notification with its model-specific Kaitai class."""
    if len(frame) != 20 or frame[0] != STATUS_HEADER:
        return None
    parsed = _parse_generated_status(frame, model)
    if parsed is None:
        return None
    return ParsedStatusEnvelope(
        int(parsed.domain),
        bytes(frame[2:-1]),
        parsed,
    )


def split_status_frame(
    frame: bytes,
    model: str = "H617A",
) -> tuple[int, bytes] | None:
    decoded = decode_status_frame(frame, model)
    if decoded is None:
        return None
    return decoded.domain, decoded.payload


def decode_command_frame(frame: bytes, model: str = "H617A") -> Any | None:
    return _parse_generated_command(frame, model)


def build_packet(cmd_type: int, action: int, params: list[int]) -> bytes:
    payload = bytearray([cmd_type, action, *params][:19])
    payload.extend(b"\x00" * (19 - len(payload)))
    payload.append(xor_checksum(payload))
    return bytes(payload)


def build_power(on: bool, model: str = "H617A") -> bytes:
    return _build_generated_power(on, model)


def build_brightness(percent: int, model: str = "H617A") -> bytes:
    return _build_generated_brightness(percent, model)


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


def build_segment_color(
    segments: Iterable[int],
    r: int,
    g: int,
    b: int,
    model: str = "H617A",
) -> bytes:
    mask = segments_to_mask(segments)
    return _build_generated_segment_colour(mask, r, g, b, model)


def build_segment_brightness(
    segments: Iterable[int],
    pct: int,
    model: str = "H617A",
) -> bytes:
    mask = segments_to_mask(segments)
    return _build_generated_segment_brightness(mask, pct, model)


def build_segment_paint(
    groups: Iterable[SegmentColorGroup],
    model: str = "H617A",
) -> list[bytes]:
    """One packet per (segments, colour) group; distinct colours require distinct packets."""
    return [build_segment_color(segments, r, g, b, model) for segments, (r, g, b) in groups]


def build_color_rgb(
    r: int,
    g: int,
    b: int,
    model: str = "H617A",
) -> bytes:
    return build_segment_color(ALL_SEGMENTS, r, g, b, model)


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


def build_color_temp(kelvin: int, model: str = "H617A") -> bytes:
    k = _clamp(kelvin, 2000, 9000)
    return _build_generated_colour_temperature(k, kelvin_to_rgb(k), model)


def build_white_brightness(percent: int, model: str = "H617A") -> bytes:
    # Whole-strip brightness: per-segment brightness command with the all-segments mask (0x7fff)
    return build_segment_brightness(ALL_SEGMENTS, percent, model)


@dataclass(frozen=True)
class ParsedStaticWrite:
    """A decoded ``33 05 15`` body (command_write::static_color / static_brightness).

    Exactly one of ``rgb``, ``kelvin`` and ``brightness_pct`` is set.
    """

    sub: int
    segment_mask: int
    rgb: tuple[int, int, int] | None = None
    kelvin: int | None = None
    kelvin_companion_rgb: tuple[int, int, int] | None = None
    brightness_pct: int | None = None

    @property
    def whole_strip(self) -> bool:
        return self.segment_mask == ALL_SEGMENTS_MASK


def parse_static_write(packet: bytes, model: str = "H617A") -> ParsedStaticWrite | None:
    """Convert a generated static command into the coordinator's semantic state."""
    generated = decode_command_frame(packet, model)
    if generated is None:
        return None
    if model == "H6199":
        if generated.opcode.name != "mode" or getattr(generated.body.sub_mode, "name", None) != "static_colour":
            return None
        detail = generated.body.detail
        operation = int(detail.operation)
        if detail.operation.name == "colour":
            rgb = (int(detail.red), int(detail.green), int(detail.blue))
            kelvin = int(detail.kelvin)
            if rgb == (0, 0, 0) and kelvin:
                preview = detail.preview
                return ParsedStaticWrite(
                    sub=operation,
                    segment_mask=int(detail.segment_mask),
                    kelvin=kelvin,
                    kelvin_companion_rgb=(int(preview.red), int(preview.green), int(preview.blue)),
                )
            return ParsedStaticWrite(
                sub=operation,
                segment_mask=int(detail.segment_mask),
                rgb=rgb,
            )
        if detail.operation.name == "brightness":
            return ParsedStaticWrite(
                sub=operation,
                segment_mask=int(detail.brightness_segment_mask),
                brightness_pct=int(detail.brightness_percent),
            )
        return None
    if generated.opcode.name != "multi" or getattr(generated.body.sub, "name", None) != "static":
        return None
    detail = generated.body.sub_body
    sub = int(detail.static_sub)
    body = detail.static_body
    if sub == STATIC_SUB_COLOR:
        rgb = (int(body.rgb_direct.red), int(body.rgb_direct.green), int(body.rgb_direct.blue))
        kelvin = int(body.kelvin)
        mask = int(body.mask.bits)
        if rgb == (0, 0, 0) and kelvin:
            return ParsedStaticWrite(
                sub=sub,
                segment_mask=mask,
                kelvin=kelvin,
                kelvin_companion_rgb=(
                    int(body.rgb_preview.red),
                    int(body.rgb_preview.green),
                    int(body.rgb_preview.blue),
                ),
            )
        return ParsedStaticWrite(sub=sub, segment_mask=mask, rgb=rgb)
    if sub == STATIC_SUB_BRIGHTNESS:
        return ParsedStaticWrite(
            sub=sub,
            segment_mask=int(body.mask.bits),
            brightness_pct=int(body.percent),
        )
    return None


def build_scene(scene_id: int) -> bytes:
    return _build_generated_h617a_scene(scene_id)


def _a3_frame(index: int, chunk: bytes) -> bytes:
    packet = bytearray([MULTI_PACKET_PREFIX, index, *chunk])
    packet = (packet + bytearray(19 - len(packet)))[:19]
    packet.append(xor_checksum(packet))
    return bytes(packet)


def build_a3_multi(type_byte: int, body: bytes, *, terminator: bool = False) -> list[bytes]:
    """Fragment a body into the two forms documented by govee_common::a3_header.

    Frames ``[0x01, linecount, type_byte, *body]`` into 17-byte chunks, each emitted as a
    20-byte ``0xA3 <index|0xFF>`` frame with an XOR checksum. Shared by scenes, music params and
    custom effects so there is a single fragmenter and a single XOR path. With ``terminator`` the
    data chunks keep sequential indices and an extra empty ``0xFF`` frame closes the sequence.

    The app never emits a lone frame: a body that fits in a single chunk is still sent as a
    numbered data frame followed by an empty ``0xFF`` terminator, so every sequence carries at
    least two frames. This is the form flat DIY (``TYPE 0x04``) uses for one- to three-colour
    palettes.

    That single-chunk rule makes ``terminator`` UNFALSIFIABLE on a one-chunk body, because
    ``chunk_count == 1`` forces the terminator either way. Finger Sketch was pinned that way and
    the flag was wrong: a two-chunk sketch captured on 2026-07-31 showed the app using the
    non-terminator form, with real data in the ``0xFF`` frame. Validate this flag only against a
    body that spans at least two chunks.
    """
    data = bytes([type_byte]) + body
    chunk_count = math.ceil((len(data) + 2) / 17)
    trailing_terminator = terminator or chunk_count == 1
    payload = bytes([0x01, chunk_count + (1 if trailing_terminator else 0)]) + data
    chunks = [payload[index : index + 17] for index in range(0, len(payload), 17)]
    last = len(chunks) - 1
    packets = [
        _a3_frame(index if trailing_terminator or index != last else 0xFF, chunk) for index, chunk in enumerate(chunks)
    ]
    if trailing_terminator:
        packets.append(_a3_frame(0xFF, b""))
    return packets


def scene_record_spans(payload: bytes) -> list[tuple[int, int]]:
    """Return the ``(start, stop)`` slice of every record in a type-2 scene body payload.

    The payload is ``<record_count> [<record_len> <record_data>]...`` (scene_body.ksy). A record
    is addressed by the catalogue config entry's explicit ``page`` number, never by that entry's
    position in the config array.
    """
    spans: list[tuple[int, int]] = []
    cursor = 1
    while cursor < len(payload):
        start = cursor + 1
        stop = start + payload[cursor]
        if stop > len(payload):
            break
        spans.append((start, stop))
        cursor = stop
    return spans


def apply_scene_speed(payload: bytes, speed: SceneSpeed, index: int) -> bytes:
    """Apply one catalogue Speed position to every field named by its config blocks.

    Only type-2 bodies are record containers, so only they carry a ``SceneSpeed`` at all; the
    generator refuses to emit one for any other body.

    The catalogue option list is authoritative over the stored param byte: Glacier 2175 ships
    0xff at both of its ``move_in`` offsets where its own list says 250, and the app rewrites
    them from the list on apply, so uploading the param verbatim runs the scene at the wrong
    speed (scene_body.ksy, confirmed live 2026-07-26). For every other page the default position
    reproduces the stored byte exactly, so this is a no-op there.
    """
    spans = scene_record_spans(payload)
    patched = bytearray(payload)
    for page in speed.pages:
        if not 0 <= page.page < len(spans):
            continue
        start, stop = spans[page.page]
        for options, offset in ((page.move_in, MOVE_IN_OFFSET), (page.move_all, MOVE_ALL_OFFSET)):
            position = stop + offset
            if not options or position < start:
                continue
            patched[position] = options[_clamp(index, 0, len(options) - 1)]
        if start + _SCENE_BRIGHTNESS_BLOCK_COUNT_OFFSET >= stop:
            continue
        brightness_block_count = payload[start + _SCENE_BRIGHTNESS_BLOCK_COUNT_OFFSET]
        if page.colour_speed:
            position = start + _SCENE_COLOUR_SPEED_BASE_OFFSET + brightness_block_count * _SCENE_BRIGHTNESS_BLOCK_SIZE
            if position < stop:
                patched[position] = page.colour_speed[_clamp(index, 0, len(page.colour_speed) - 1)]
        for brightness in page.brightness_speeds:
            if not 0 <= brightness.block < brightness_block_count or not brightness.values:
                continue
            position = start + _SCENE_FIRST_BRIGHTNESS_SPEED_OFFSET + brightness.block * _SCENE_BRIGHTNESS_BLOCK_SIZE
            if position < stop:
                patched[position] = brightness.values[_clamp(index, 0, len(brightness.values) - 1)]
    return bytes(patched)


def build_scene_multi(
    scene_param_b64: str,
    scene_code: int,
    scene_type: int = 2,
    speed: SceneSpeed | None = None,
    speed_index: int | None = None,
) -> list[bytes]:
    if not scene_param_b64:
        return [build_scene(scene_code)]
    payload = base64.b64decode(scene_param_b64)
    if speed is not None:
        payload = apply_scene_speed(payload, speed, speed.default_index if speed_index is None else speed_index)
    return [*build_a3_multi(scene_type, payload), build_scene(scene_code)]


def build_h6199_scene(scene_code: int, music_code: int = 0) -> list[bytes]:
    """Build one H6199 activation with linked scene music disabled by default."""
    return [_build_generated_h6199_scene(scene_code, music_code)]


def build_h6199_scene_multi(
    scene_param_b64: str,
    scene_code: int,
    scene_type: int,
    music_code: int = 0,
) -> list[bytes]:
    packets = build_a3_multi(scene_type, base64.b64decode(scene_param_b64)) if scene_param_b64 else []
    return [*packets, *build_h6199_scene(scene_code, music_code)]


STATE_QUERY = _build_generated_power_query()
BRIGHTNESS_QUERY = _build_generated_brightness_query()
COLOR_MODE_QUERY = _build_generated_colour_mode_query()
WHITE_BALANCE_QUERY = _build_generated_white_balance_query()
BLANK_SCREEN_QUERY = _build_generated_blank_screen_query()
RELATIVE_BRIGHTNESS_QUERY = _build_generated_relative_brightness_query()
FW_QUERY = _build_generated_firmware_query()
HW_QUERY = _build_generated_hardware_query()
KEEP_ALIVE = STATE_QUERY


def build_video_mode(
    full_screen: bool = True,
    game_mode: bool = False,
    saturation: int = 100,
    sound_effects: bool = False,
    sound_effects_softness: int = 100,
) -> bytes:
    """Build the H6199 video-mode write (h6199_command_write::video_body).

    Note the polarity of the picture profile, which is the opposite way round to the order the
    app lists the two in: Game is 1 and Movie is 0. Saturation and softness are direct percents
    on this model, not 0..255 levels. Softness keeps its captured floor of 1 and persists while
    sound effects are off, which is the form every captured write takes.
    """
    return _build_generated_video(
        full_screen,
        game_mode,
        saturation,
        sound_effects,
        sound_effects_softness,
    )


# The app's complete white-balance strip, in cool-to-warm order. Every position was captured
# independently on the H6199 on 2026-08-05. Direct HA trials also proved the firmware accepts
# independent off-table gains exactly, but the normal entity mirrors the vendor's calibrated curve.
WHITE_BALANCE_POSITIONS: tuple[tuple[int, int], ...] = (
    (7, 10),
    (8, 8),
    (9, 5),
    (10, 8),
    (10, 6),
    (11, 6),
    (12, 7),
    (12, 6),
    (13, 5),
    (13, 3),
    (14, 5),
    (14, 3),
    (15, 4),
    (15, 3),
    (16, 5),
    (16, 4),
    (16, 3),
    (18, 6),
    (18, 4),
    (21, 5),
)
# The pair the app's own Reset button writes (h6199_white_balance_reset), which is table entry 16.
# This is where a caller starts from, not what a device currently reports; the aa a9 read-back
# carries the reset reference and current pair separately.
WHITE_BALANCE_RESET: tuple[int, int] = WHITE_BALANCE_POSITIONS[16]


def build_video_white_balance(red: int, blue: int) -> bytes:
    """Build the H6199 white-balance write (h6199_command_write::white_balance_payload).

    The two bytes are independent gains. The app's normal marker picks one of
    ``WHITE_BALANCE_POSITIONS``, while direct H6199 trials proved off-table pairs are also accepted
    and read back exactly.

    ``manual`` is written as the 1 every captured write carries. It is not exposed: its name rests
    on the vendor app's encoder rather than on a capture that varied it, and no capture has yet
    been taken with Auto White Balance on.
    """
    return _build_generated_white_balance(red, blue)


def build_blank_screen(enabled: bool) -> bytes:
    """Build the H6199 blank-screen display setting (h6199_command_write::blank_screen_payload).

    Only the flag is ours to set. The five bytes after it are replayed from capture: they never
    moved across either write, and the vendor app's reading of them as a flag and two integers
    names nothing this project can vary.
    """
    return _build_generated_blank_screen(enabled)


def build_relative_brightness(percent: int) -> bytes:
    """Build the H6199 relative-brightness write (h6199_command_write::relative_brightness_body).

    This compatibility form gives every edge the same percentage. Use
    :func:`build_relative_brightness_edges` when the edges differ.
    """
    level = _clamp(percent, 0, 100)
    return build_relative_brightness_edges(level, level, level, level)


def build_relative_brightness_edges(left: int, top: int, right: int, bottom: int) -> bytes:
    """Build independent H6199 edge brightness values in captured left/top/right/bottom order."""
    return _build_generated_relative_brightness(left, top, right, bottom)


def build_music_mode_with_color(
    mode_id: int,
    sensitivity: int = 99,
    color: tuple[int, int, int] | None = None,
    calm: bool = False,
    model: str = "H617A",
) -> bytes:
    return _build_generated_music(
        mode_id,
        sensitivity,
        color,
        calm,
        model,
    )


# --- H617A music per-mode movement parameters --------------------------------------------------
# music_body.ksy owns the body and per-mode tails. Every template byte below is replayed from
# captured bodies; the coordinator overlays only fields that grammar names.
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
    # Piano Keys 0x34: report step music-p-keys (= pcap idx20); [27]=key count 15, [30]=derived floor(count/2).
    0x34: bytes.fromhex("3407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000"),
    # Fountain 0x35: current iOS Clockwise baseline. [26] is the real direction control
    # (CW 0x00 / Two-way 0x01 / CCW 0x02); [28] is NOT a second direction byte, it is a
    # piece count the app derives from the segment count -- segments/3, or segments/4 when
    # [26] == 1. Writing the two together is therefore correct and matches the app, but they
    # are a control and its consequence, not a pair. See music_body.ksy::fountain_tail.
    0x35: bytes.fromhex("3507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0001055000000000"),
    # Day & Night 0x37: pcap baseline idx27/29; [26]=segments 1, [27]=speed 10 (reproduces both A/B frames).
    0x37: bytes.fromhex("3707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000"),
}
# mode -> captured palette colour count (body-local byte 1); guards palette overrides so the
# `<RGB x count>` region can never shift the downstream param offsets.
_MUSIC_PARAM_COUNT: dict[int, int] = {mode: body[1] for mode, body in _MUSIC_PARAM_TEMPLATE.items()}
_MUSIC_PARAM_BASE = 3  # assembled-body base: template byte 0 is the MODE byte at assembled index 3.


def build_music_params_a3(
    mode: int,
    overrides: dict[int, int],
    palette: list[tuple[int, int, int]] | None = None,
) -> list[bytes]:
    """Build the H617A per-mode music movement frame (command 0x41, fragmented over a3).

    Replays the capture-pinned template for ``mode`` verbatim, overlaying only the decoded param
    offsets in ``overrides`` (a3-absolute; the coordinator supplies both the user-facing params and
    the derived companion/half bytes). A palette whose length differs from the captured count is
    rejected so the ``<RGB x count>`` region cannot shift the downstream offsets.
    """
    body = bytearray(_MUSIC_PARAM_TEMPLATE[mode])
    if palette is not None:
        if len(palette) != _MUSIC_PARAM_COUNT[mode]:
            raise ValueError("palette count does not match the captured mode template")
        body[2 : 2 + 3 * len(palette)] = bytes(channel for rgb in palette for channel in rgb)
    for offset, value in overrides.items():
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
    scene_code: int | None = None
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
    multi_effect_flag: int | None = None


def parse_generated_color_mode(
    generated: Any,
    model: str,
) -> ParsedColorModeResponse:
    body = generated.body
    mode = int(body.mode)
    if model == "H6199":
        if mode == COLOR_MODE_VIDEO:
            detail = body.detail
            return ParsedColorModeResponse(
                mode=ParsedMode.VIDEO,
                video_mode="game" if int(detail.source) == 1 else "movie",
                video_full_screen=int(detail.region) == 1,
                video_saturation=int(detail.saturation),
                video_sound_effects=bool(detail.sound_effects),
                video_sound_effects_softness=int(detail.softness),
            )
        if mode == COLOR_MODE_MUSIC:
            detail = body.detail
            fixed_colour = None
            if detail.has_fixed_colour:
                fixed_colour = (
                    int(detail.fixed_colour.red),
                    int(detail.fixed_colour.green),
                    int(detail.fixed_colour.blue),
                )
            return ParsedColorModeResponse(
                mode=ParsedMode.MUSIC,
                music_mode=MUSIC_SLUG_BY_ID.get(int(detail.mode)),
                music_sensitivity=int(detail.sensitivity),
                music_calm=bool(detail.is_calm),
                music_color=fixed_colour,
            )
        if mode == COLOR_MODE_SCENE:
            scene_code = int(body.detail.scene_id)
            return ParsedColorModeResponse(
                mode=ParsedMode.SCENE,
                effect=SCENE_EFFECT_BY_MODEL_ID["H6199"].get(scene_code),
                scene_code=scene_code,
            )
        if mode == COLOR_MODE_STATIC:
            return ParsedColorModeResponse(mode=ParsedMode.COLOUR)
        return ParsedColorModeResponse(mode=ParsedMode.UNKNOWN)

    if mode == COLOR_MODE_SCENE:
        scene_code = int(body.mode_body.scene_id)
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE,
            effect=SCENE_EFFECT_BY_MODEL_ID["H617A"].get(scene_code),
            scene_code=scene_code,
        )
    if mode == COLOR_MODE_DIY:
        return ParsedColorModeResponse(
            mode=ParsedMode.DIY,
            diy_slot=int(body.mode_body.slot),
        )
    if mode == COLOR_MODE_MUSIC:
        detail = body.mode_body
        music_color = None
        if detail.manual_color_count >= 1:
            music_color = (
                int(detail.rgb.red),
                int(detail.rgb.green),
                int(detail.rgb.blue),
            )
        return ParsedColorModeResponse(
            mode=ParsedMode.MUSIC,
            music_mode=MUSIC_SLUG_BY_ID.get(int(detail.mode_id)),
            music_sensitivity=int(detail.sensitivity),
            music_calm=bool(detail.style) if int(detail.mode_id) == RHYTHM_MODE_ID else None,
            music_color=music_color,
        )
    if mode == COLOR_MODE_STATIC:
        return ParsedColorModeResponse(
            mode=ParsedMode.COLOUR,
            multi_effect_flag=int(body.mode_body.sub),
        )
    return ParsedColorModeResponse(mode=ParsedMode.UNKNOWN)
