"""Govee BLE protocol — 20-byte packets with XOR checksum at byte 19."""

import base64
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, IntEnum, auto
from typing import Any, cast

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
    build_h617a_diy as _build_generated_h617a_diy,
)
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
# The DIY slot is an app-assigned per-entry id echoed back by aa 05 0a, not an addressing scheme we
# own; see govee_common::diy_selector. Only two values are genuinely reserved, and both are fixed by
# the editor SURFACE rather than by any entry: Finger Sketch always 0x20, Colour > Vibrant always
# 0x84. 0xF0 is NOT reserved - the spec records it as the id of one saved user DIY on the capture
# account, alongside 0x17, 0x32, 0x98 and 0xBE. We must still name a slot when activating content we
# author ourselves, so we reuse that observed id and accept that the vendor app may label our effect
# with whatever entry holds it. Named for what it is rather than "default", which invited the reading
# that it was a safe scratch value.
AUTHORED_DIY_SLOT = 0xF0
SKETCH_DIY_SLOT = 0x20
VIBRANT_DIY_SLOT = 0x84


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


def _get(payload: bytes, index: int) -> int | None:
    return payload[index] if len(payload) > index else None


@dataclass(frozen=True, slots=True)
class ParsedStatusEnvelope:
    domain: int
    payload: bytes
    generated: Any | None


def decode_status_frame(
    frame: bytes,
    model: str = "H617A",
) -> ParsedStatusEnvelope | None:
    """Split an incoming status notification into ``(domain, payload)``.

    Returns ``None`` for frames shorter than three bytes, without the status header, or
    for a full envelope whose XOR checksum is invalid. Short notifications have no
    checksum byte and keep everything after the domain.
    """
    if len(frame) < 3 or frame[0] != STATUS_HEADER:
        return None
    if len(frame) == 20:
        parsed = _parse_generated_status(frame, model)
        if parsed is None:
            return None
        return ParsedStatusEnvelope(
            int(parsed.domain),
            bytes(frame[2:-1]),
            parsed,
        )
    return ParsedStatusEnvelope(frame[1], bytes(frame[2:]), None)


def split_status_frame(
    frame: bytes,
    model: str = "H617A",
) -> tuple[int, bytes] | None:
    decoded = decode_status_frame(frame, model)
    if decoded is None:
        return None
    return decoded.domain, decoded.payload


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


def parse_static_write(packet: bytes) -> ParsedStaticWrite | None:
    """Read back a ``33 05 15`` frame this module built, or None if it is not one.

    The inverse of build_segment_color / build_color_temp / build_segment_brightness. Callers
    that need these fields must come through here rather than index the frame themselves: the
    offsets belong to command_write::static_color, and every private copy of them is free to
    drift. One already had. Sub 0x03 is documented but unbuilt, so it reads as None.
    """
    if len(packet) < 4 or packet[0] != COMMAND_HEADER or packet[1] != COLOR_PACKET_TYPE:
        return None
    if packet[2] != COLOR_MODE_STATIC:
        return None
    sub = packet[3]
    if sub == STATIC_SUB_COLOR and len(packet) >= 14:
        rgb = (packet[4], packet[5], packet[6])
        kelvin = (packet[7] << 8) | packet[8]
        mask = packet[12] | (packet[13] << 8)
        # A colour-temperature set zeroes the direct RGB and carries a preview instead; a direct
        # paint zeroes the kelvin. A deliberate black paint is rgb, not a 0 K temperature.
        if rgb == (0, 0, 0) and kelvin:
            return ParsedStaticWrite(
                sub=sub,
                segment_mask=mask,
                kelvin=kelvin,
                kelvin_companion_rgb=(packet[9], packet[10], packet[11]),
            )
        return ParsedStaticWrite(sub=sub, segment_mask=mask, rgb=rgb)
    if sub == STATIC_SUB_BRIGHTNESS and len(packet) >= 7:
        return ParsedStaticWrite(sub=sub, segment_mask=packet[5] | (packet[6] << 8), brightness_pct=packet[4])
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


# --- Custom-effect content encoders -------------------------------------------------------------
# Every builder returns list[bytes]; the store/entity layers never see raw bytes. Packet bytes
# live only here, with body layouts owned by diy_type03.ksy and diy_type04.ksy.


def build_diy_activate(slot: int, type_byte: int | None = None) -> bytes:
    """Build the selector documented by govee_common::diy_selector.

    ``slot`` is app-assigned. Finger Sketch appends its captured type byte; the other
    current builders omit it.
    """
    return _build_generated_h617a_diy(slot, type_byte)


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
    # VALIDATED: Finger Sketch live H617A 3.02.24 (2026-07-16) and app 7.2.10 (2026-07-31).
    # The 2026-07-31 capture is the one that pins the framing: its body needs TWO chunks, and
    # only a two-chunk body can tell the two A3 forms apart. The 2026-07-16 body fitted in one,
    # where build_a3_multi forces a terminator whatever the flag says, so `terminator=True`
    # rode along unfalsifiable and wrong for every larger sketch.
    body = bytes([content.motion, content.speed, content.brightness, *content.background])
    groups = _group_by_colour_0based(content.colors)
    body += bytes([len(groups)])
    for rgb, indices in groups:
        body += bytes([len(indices), *rgb, *indices])
    return [*build_a3_multi(0x03, body), build_diy_activate(SKETCH_DIY_SLOT, 0x03)]


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
    # VALIDATED: flat DIY live H617A 3.02.24; TYPE 0x04 body + 33 05 0a <slot>, two-frame envelope.
    palette = b"".join(bytes(colour) for colour in content.palette)
    body = bytes([content.family, content.variant, content.speed, len(palette)]) + palette
    return [*build_a3_multi(0x04, body), build_diy_activate(AUTHORED_DIY_SLOT)]


def build_combo(content: ComboContent, *, slot: int = AUTHORED_DIY_SLOT) -> list[bytes]:
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


STATE_QUERY = _build_generated_power_query()
BRIGHTNESS_QUERY = _build_generated_brightness_query()
COLOR_MODE_QUERY = _build_generated_colour_mode_query()
WHITE_BALANCE_QUERY = _build_generated_white_balance_query()
BLANK_SCREEN_QUERY = _build_generated_blank_screen_query()
RELATIVE_BRIGHTNESS_QUERY = _build_generated_relative_brightness_query()
FW_QUERY = _build_generated_firmware_query()
HW_QUERY = _build_generated_hardware_query()
SLEEP_TIMER_QUERY = build_packet(STATUS_HEADER, 0x11, [])
WAKEUP_TIMER_QUERY = build_packet(STATUS_HEADER, 0x12, [])
SCHEDULE_TIMER_QUERY = build_packet(STATUS_HEADER, 0x23, [])
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
            raise EffectValidationError("palette_count_mismatch")
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


@dataclass(frozen=True)
class ParsedDisplaySettingResponse:
    """Decoded ``aa a9`` display-setting state."""

    setting: int
    reset_white_balance: tuple[int, int] | None = None
    current_white_balance: tuple[int, int] | None = None
    blank_screen: bool | None = None


@dataclass(frozen=True)
class ParsedRelativeBrightnessResponse:
    """Decoded ``aa ae`` edge state in captured left/top/right/bottom order."""

    left: int
    top: int
    right: int
    bottom: int


def parse_display_setting_response(payload: bytes) -> ParsedDisplaySettingResponse:
    """Decode an ``aa a9`` display-setting reply."""
    if len(payload) < 2:
        raise ValueError("Display-setting payload is truncated")
    setting, declared_length = payload[:2]
    body = payload[2 : 2 + declared_length]
    if len(body) != declared_length:
        raise ValueError("Display-setting payload length does not match its declaration")
    if setting == DISPLAY_SETTING_WHITE_BALANCE:
        if len(body) != 6:
            raise ValueError("White-balance state must contain reset and current triples")
        return ParsedDisplaySettingResponse(
            setting=setting,
            reset_white_balance=(body[1], body[2]),
            current_white_balance=(body[4], body[5]),
        )
    if setting == DISPLAY_SETTING_BLANK_SCREEN:
        if len(body) != 6:
            raise ValueError("Blank-screen state must contain its six-byte payload")
        return ParsedDisplaySettingResponse(setting=setting, blank_screen=bool(body[0]))
    return ParsedDisplaySettingResponse(setting=setting)


def parse_relative_brightness_response(payload: bytes) -> ParsedRelativeBrightnessResponse:
    """Decode an ``aa ae`` edge-state reply."""
    if len(payload) < 6 or payload[0] != RELATIVE_BRIGHTNESS_HEAD or payload[1] != RELATIVE_BRIGHTNESS_EDGES:
        raise ValueError("Relative-brightness state has an unsupported shape")
    left, top, right, bottom = payload[2:6]
    return ParsedRelativeBrightnessResponse(left, top, right, bottom)


def parse_color_mode_response(
    payload: bytes, *, static_echoes_color: bool = False, video_supported: bool = False
) -> ParsedColorModeResponse:
    """Decode an ``aa 05`` colour-mode reply.

    The flags describe model-specific read-back behaviour. Callers with a
    :class:`~.const.ModelProfile` pass its capabilities.
    """
    if not payload:
        raise ValueError("Color mode payload is empty")
    mode = payload[0]
    if mode == COLOR_MODE_SCENE:
        scene_bytes = payload[1:] or b"\x00"
        while len(scene_bytes) > 1 and scene_bytes[-1] == 0:
            scene_bytes = scene_bytes[:-1]
        scene_code = int.from_bytes(scene_bytes, "little")
        return ParsedColorModeResponse(
            mode=ParsedMode.SCENE, effect=SCENE_EFFECT_BY_ID.get(scene_code), scene_code=scene_code
        )
    if mode == COLOR_MODE_DIY:
        return ParsedColorModeResponse(mode=ParsedMode.DIY, diy_slot=_get(payload, 1))
    if mode == COLOR_MODE_VIDEO:
        # The video selector is 0x00, so any short or zero-led aa 05 frame lands here, and
        # split_status_frame passes loose frames through without verifying their checksum. On a
        # model with no video mode that reads out as a confident "game, saturation N" from noise.
        if not video_supported:
            return ParsedColorModeResponse(mode=ParsedMode.UNKNOWN)
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
    if not static_echoes_color:
        # status_reply::cm_static. The byte after the mode is NOT a static sub-selector: it mirrors
        # the 33 a3 register, and the rest of the window is always zero. Reading a colour out of it
        # invents (0, 0, 0) whenever that register is set.
        return ParsedColorModeResponse(mode=ParsedMode.COLOUR, multi_effect_flag=_get(payload, 1))
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


# Timer encoders are capture-backed by govee_common::{sleep_timer,wake_timer} and
# command_write::timer_schedule_cmd. Power-off memory remains an unsupported research lead.


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
    if not 0 <= index <= 3:
        raise ValueError(f"timer slot {index} out of range 0..3")
    enable_and_type = (0x80 if enabled else 0x00) | (0x01 if on_action else 0x00)
    params = [index, enable_and_type, _clamp(hour, 0, 23), _clamp(minute, 0, 59), timer_repeat(repeat_days)]
    return build_packet(0x33, 0x23, params)


def build_timer_sleep(enabled: bool, start_brightness: int, close_minutes: int, current_minutes: int = 0) -> bytes:
    """Build a sleep/fade-off timer (0x11): fade from start_brightness over close_minutes."""
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
    """Build a power-off memory toggle (0x41): restore last state after power loss.

    PROVEN ABSENT ON THE H617A. 2026-07-29: this opcode is not acknowledged. In a single
    connection, 33 04 and 33 01 both acked either side of two 33 41 writes that did not,
    and every other command opcode used that session acked as well. The device does not
    recognise 0x41 in either direction; aa 41 answers nothing before or after a write.

    Unreachable anyway, since no ModelProfile sets supports_poweroff_memory. Kept for a
    model that does have it, not for this one. An external fuzz reports 0x41 as power-off
    memory on a different SKU, which is a lead for that SKU only.

    AND THE H617A DOES NOT NEED IT: IT RESTORES ITS PRIOR STATE UNCONDITIONALLY. Observed
    2026-07-29 with mains power cut for about fifteen seconds and a person watching. The
    strip was staged on, solid blue, brightness 1%, and came back on, solid blue, at 1%,
    with aa 01, aa 04, aa 05 and aa a3 all reading their pre-cut values. So the absence of
    a configurable toggle is not the absence of the behaviour, and nothing about this
    device's restore behaviour should be read as evidence about opcode 0x41 either way.

    ONE THING ONLY EYES COULD SEE: before applying the saved state the firmware runs a
    power-on self-test, sweeping red then green then blue at near-full brightness for a
    moment. It is transient, so any read taken after settling shows only the restored
    state and misses it entirely.
    """
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
    """Decode a power-off memory aa 41 reply [enabled, mode].

    NO SUCH REPLY EXISTS ON THE H617A, and the unset-versus-unsupported confound is now
    closed. 2026-07-29: aa 41 was queried before and after a 33 41 01 write and answered
    nothing either time, and the write itself was never acknowledged while controls in the
    same connection were. So the register cannot be read AND cannot be written here.
    """
    # EXPERIMENTAL: harness=TBD encoding=decode-only
    if not payload:
        raise ValueError("power-off memory payload is empty")
    return ParsedPowerOffMemory(enabled=bool(payload[0]), mode=_get(payload, 1))


# Every public builder/parser and query constant cites its canonical Kaitai structure.
# VALIDATED means the current byte layout is capture-backed. EXPERIMENTAL is reserved for
# unreachable research leads and requires a matching source marker on the function.
@dataclass(frozen=True)
class Evidence:
    """Where a builder's byte layout is proven, and whether it is VALIDATED or EXPERIMENTAL."""

    status: str
    source: str


BUILDER_EVIDENCE: dict[str, Evidence] = {
    "build_packet": Evidence(
        "VALIDATED",
        "command_write.ksy and h6199_command_write.ksy roots; 20-byte XOR envelopes",
    ),
    "build_power": Evidence(
        "VALIDATED",
        "command_write.ksy::power_cmd and h6199_command_write.ksy::power_body",
    ),
    "build_brightness": Evidence(
        "VALIDATED",
        "command_write.ksy::brightness_cmd and h6199_command_write.ksy::brightness_body",
    ),
    "build_segment_color": Evidence(
        "VALIDATED",
        "command_write.ksy::static_color and h6199_command_write.ksy::static_colour_body",
    ),
    "build_segment_brightness": Evidence(
        "VALIDATED",
        "command_write.ksy::static_brightness and h6199_command_write.ksy::static_colour_body operation brightness",
    ),
    "build_segment_paint": Evidence(
        "VALIDATED",
        "command_write.ksy::static_color; one captured frame per colour group",
    ),
    "build_color_rgb": Evidence(
        "VALIDATED",
        "command_write.ksy::static_color and h6199_command_write.ksy::static_colour_body",
    ),
    "build_color_temp": Evidence(
        "VALIDATED",
        "command_write.ksy::static_color and h6199_command_write.ksy::static_colour_body; "
        "Kelvin and mask are capture-backed, while the companion RGB algorithm remains non-vendor-exact",
    ),
    "build_white_brightness": Evidence(
        "VALIDATED",
        "command_write.ksy::static_brightness with the all-segments mask",
    ),
    "build_scene": Evidence(
        "VALIDATED",
        "command_write.ksy::scene_activate",
    ),
    "build_a3_multi": Evidence(
        "VALIDATED",
        "govee_common.ksy::a3_header and the body specs importing it",
    ),
    "build_scene_multi": Evidence(
        "VALIDATED",
        "scene_body.ksy, scene_type1_body.ksy and command_write.ksy::scene_activate",
    ),
    "build_h6199_scene": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::scene_body class-1 built-in activations",
    ),
    "build_diy_activate": Evidence(
        "VALIDATED",
        "govee_common.ksy::diy_selector via command_write.ksy::multi_cmd",
    ),
    "build_segment_content": Evidence(
        "VALIDATED",
        "command_write.ksy::{static_color,static_brightness} dispatcher",
    ),
    "build_sketch": Evidence(
        "VALIDATED",
        "diy_type03.ksy plus govee_common.ksy::diy_selector",
    ),
    "build_vibrant": Evidence(
        "VALIDATED",
        "diy_type03.ksy Vibrant body plus govee_common.ksy::diy_selector",
    ),
    "build_flat_diy": Evidence(
        "VALIDATED",
        "diy_type04.ksy::flat_body plus govee_common.ksy::diy_selector",
    ),
    "build_combo": Evidence(
        "VALIDATED",
        "diy_type04.ksy::combo_body plus govee_common.ksy::diy_selector",
    ),
    "build_custom_effect": Evidence(
        "VALIDATED",
        "command_write.ksy, diy_type03.ksy and diy_type04.ksy per-kind dispatch",
    ),
    "build_music_mode_with_color": Evidence(
        "VALIDATED",
        "govee_common.ksy::music_selector and h6199_command_write.ksy::music_body",
    ),
    "build_music_params_a3": Evidence(
        "VALIDATED",
        "music_body.ksy root and mode-specific tail types",
    ),
    "build_video_mode": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::video_body",
    ),
    "build_video_white_balance": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::white_balance_payload",
    ),
    "build_blank_screen": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::blank_screen_payload",
    ),
    "build_relative_brightness": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::relative_brightness_body",
    ),
    "build_relative_brightness_edges": Evidence(
        "VALIDATED",
        "h6199_command_write.ksy::relative_brightness_body per-edge differentials",
    ),
    "build_timer_schedule": Evidence(
        "VALIDATED",
        "command_write.ksy::timer_schedule_cmd and govee_common.ksy::timer_slot",
    ),
    "build_timer_sleep": Evidence(
        "VALIDATED",
        "govee_common.ksy::sleep_timer through command_write.ksy",
    ),
    "build_timer_wakeup": Evidence(
        "VALIDATED",
        "govee_common.ksy::wake_timer through command_write.ksy",
    ),
    "build_poweroff_memory": Evidence(
        "EXPERIMENTAL",
        "status_reply.ksy documents the absent H617A aa 41 reply; no supporting write grammar",
    ),
    "split_status_frame": Evidence(
        "VALIDATED",
        "status_reply.ksy and h6199_status_reply.ksy roots",
    ),
    "parse_static_write": Evidence(
        "VALIDATED",
        "command_write.ksy::{static_color,static_brightness}",
    ),
    "parse_color_mode_response": Evidence(
        "VALIDATED",
        "status_reply.ksy::colormode_body and h6199_status_reply.ksy::colour_mode_body",
    ),
    "parse_display_setting_response": Evidence(
        "VALIDATED",
        "h6199_status_reply.ksy::display_setting_body",
    ),
    "parse_relative_brightness_response": Evidence(
        "VALIDATED",
        "h6199_status_reply.ksy::relative_brightness_body",
    ),
    "parse_fw_version": Evidence(
        "VALIDATED",
        "status_reply.ksy::version_body and h6199_status_reply.ksy::version_body",
    ),
    "parse_hw_version": Evidence(
        "VALIDATED",
        "status_reply.ksy::hw_version_body and h6199_status_reply.ksy::hardware_version_body",
    ),
    "parse_timer_repeat": Evidence(
        "VALIDATED",
        "govee_common.ksy::{timer_slot,wake_timer}",
    ),
    "parse_timer_schedule": Evidence(
        "VALIDATED",
        "govee_common.ksy::timer_slot",
    ),
    "parse_timer_schedule_table": Evidence(
        "VALIDATED",
        "status_reply.ksy::timer_body",
    ),
    "parse_timer_sleep": Evidence(
        "VALIDATED",
        "govee_common.ksy::sleep_timer through status_reply.ksy",
    ),
    "parse_timer_wakeup": Evidence(
        "VALIDATED",
        "govee_common.ksy::wake_timer through status_reply.ksy",
    ),
    "parse_poweroff_memory": Evidence(
        "EXPERIMENTAL",
        "status_reply.ksy documents the absent H617A aa 41 reply; parser shape is unobserved",
    ),
    "STATE_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::power_body query envelope; query/reply direction is external",
    ),
    "BRIGHTNESS_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::brightness_body query envelope; query/reply direction is external",
    ),
    "COLOR_MODE_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::colormode_body and h6199_status_query.ksy::zero_body",
    ),
    "WHITE_BALANCE_QUERY": Evidence(
        "VALIDATED",
        "h6199_status_query.ksy::display_setting_query_body white_balance",
    ),
    "BLANK_SCREEN_QUERY": Evidence(
        "VALIDATED",
        "h6199_status_query.ksy::display_setting_query_body blank_screen",
    ),
    "RELATIVE_BRIGHTNESS_QUERY": Evidence(
        "VALIDATED",
        "h6199_status_query.ksy::relative_brightness_query_body",
    ),
    "FW_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::version_body query envelope and h6199_status_query.ksy::zero_body",
    ),
    "HW_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::hw_version_body query envelope and h6199_status_query.ksy::hardware_query_body",
    ),
    "SLEEP_TIMER_QUERY": Evidence(
        "VALIDATED",
        "govee_common.ksy::sleep_timer query envelope through status_reply.ksy",
    ),
    "WAKEUP_TIMER_QUERY": Evidence(
        "VALIDATED",
        "govee_common.ksy::wake_timer query envelope through status_reply.ksy",
    ),
    "SCHEDULE_TIMER_QUERY": Evidence(
        "VALIDATED",
        "status_reply.ksy::timer_body query envelope",
    ),
    "KEEP_ALIVE": Evidence(
        "VALIDATED",
        "status_reply.ksy::power_body query envelope; identical to STATE_QUERY",
    ),
}
