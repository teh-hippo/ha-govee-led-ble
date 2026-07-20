"""Server-rendered effect-preview renderer (pure: no HA, no BLE, sends nothing to the device).

Maps the currently-selected look to an ``segment_count``-wide RGB matrix (one row per animation
frame) and encodes it to PNG (a single representative still) or an animated GIF (a bounded motion
loop). The colour maths reuses the encoder's ``_interpolate`` so a Vibrant preview matches the wire
gradient exactly; sketch/flat/combo/scene motion is an approximate, deterministic model (previews
carry no protocol-provability burden). All rendering is pure and unit-tested apart from encoding.
"""

import colorsys
import hashlib
import io
import json
import math
from dataclasses import dataclass
from typing import Any

from .custom_effects import (
    RGB,
    ComboContent,
    EffectContent,
    FlatContent,
    SegmentContent,
    SketchContent,
    UnknownContent,
    VibrantContent,
    content_to_dict,
)
from .protocol import _VIBRANT_GAMMA, _interpolate
from .scenes import SceneEntry

type Frame = list[RGB]  # one animation frame: segment_count RGB cells, left to right
type FrameMatrix = list[Frame]  # frames x segment_count
type PreviewLook = EffectContent | SceneEntry  # a custom content object, or a built-in scene

_OFF: RGB = (0, 0, 0)
_WHITE: RGB = (255, 255, 255)

_LOOP_FRAMES = 12  # bounded animation loop length when motion is on
_STILL_FRAME = _LOOP_FRAMES // 2  # representative mid-animation frame used under reduce-motion
_FRAME_DURATION_MS = 120  # GIF per-frame duration
_CELL_PX = 16  # rendered width of one segment
_HEIGHT_PX = 48  # rendered image height
_BREATHE_FLOOR = 0.3  # dimmest breathe/music frame (never fully dark)
_TWINKLE_FLOOR = 0.25
_TWINKLE_PHASE = 0.37  # per-segment twinkle phase offset

# CAT 2.4 Finger Sketch motion codes grouped into approximate preview motions.
_ROTATE_LEFT = frozenset({0x0A})  # counter-clockwise
_BREATHE_MOTION = frozenset({0x14})  # breathe
_TWINKLE_MOTION = frozenset({0x0F})  # twinkle
# clockwise 0x09, cycle 0x02 and gradient 0x13 fall through to a right rotation.

# CAT 2.6 flat DIY motion families mapped to an approximate preview style.
_FLAT_STYLE: dict[int, str] = {
    0x00: "fade",  # Fade: smooth palette cross-fade across the whole strip
    0x01: "jump",  # Jumping: hard palette steps
    0x02: "twinkle",  # Twinkle
    0x03: "marquee",  # Marquee: tiled palette blocks scrolling
    0x04: "breathe",  # Music: gradient breathing
    0x08: "chase",  # Chasing: a single lit cell running along
    0x09: "gradient",  # Rainbow: scrolling gradient
    0x0A: "gradient",  # Crossing: scrolling gradient
}
_DEFAULT_FLAT_STYLE = "gradient"


def _clamp_channel(value: float) -> int:
    return max(0, min(255, round(value)))


def _scale(colour: RGB, factor: float) -> RGB:
    return (_clamp_channel(colour[0] * factor), _clamp_channel(colour[1] * factor), _clamp_channel(colour[2] * factor))


def _shift(frame_index: int, segment_count: int) -> int:
    """Whole-segment offset for ``frame_index`` so the loop completes one revolution."""
    return round(frame_index * segment_count / _LOOP_FRAMES)


def _rotate(row: Frame, offset: int) -> Frame:
    count = len(row)
    return [row[(index - offset) % count] for index in range(count)]


def _breathe_factor(frame_index: int) -> float:
    wave = 0.5 + 0.5 * math.cos(math.tau * frame_index / _LOOP_FRAMES)
    return _BREATHE_FLOOR + (1.0 - _BREATHE_FLOOR) * wave


def _twinkle_factor(frame_index: int, segment_index: int) -> float:
    phase = frame_index / _LOOP_FRAMES + segment_index * _TWINKLE_PHASE
    wave = 0.5 + 0.5 * math.cos(math.tau * phase)
    return _TWINKLE_FLOOR + (1.0 - _TWINKLE_FLOOR) * wave


def _palette_gradient(palette: tuple[RGB, ...], segment_count: int) -> Frame:
    if not palette:
        return [_WHITE] * segment_count
    return list(_interpolate(palette, segment_count))


def _palette_tile(palette: tuple[RGB, ...], segment_count: int) -> Frame:
    if not palette:
        return [_WHITE] * segment_count
    return [palette[index * len(palette) // segment_count] for index in range(segment_count)]


def _palette_cycle_colour(palette: tuple[RGB, ...], frame_index: int, *, smooth: bool) -> RGB:
    if not palette:
        return _WHITE
    if len(palette) == 1:
        return palette[0]
    position = frame_index * len(palette) / _LOOP_FRAMES
    lower = int(position) % len(palette)
    if not smooth:
        return palette[lower]
    fraction = position - int(position)
    upper = (lower + 1) % len(palette)
    start, end = palette[lower], palette[upper]
    return (
        _clamp_channel(start[0] + (end[0] - start[0]) * fraction),
        _clamp_channel(start[1] + (end[1] - start[1]) * fraction),
        _clamp_channel(start[2] + (end[2] - start[2]) * fraction),
    )


def _cell_or(colours: tuple[RGB | None, ...], index: int, fallback: RGB) -> RGB:
    cell = colours[index] if index < len(colours) else None
    return cell if cell is not None else fallback


def _render_segments(content: SegmentContent, segment_count: int) -> Frame:
    return [_cell_or(content.colors, index, _OFF) for index in range(segment_count)]


def _render_vibrant(content: VibrantContent, segment_count: int) -> Frame:
    if not content.stops:
        return [_OFF] * segment_count
    return list(_interpolate(content.stops, segment_count, gamma=_VIBRANT_GAMMA))


def _render_sketch(content: SketchContent, segment_count: int, frame_index: int) -> Frame:
    base: Frame = [_cell_or(content.colors, index, content.background) for index in range(segment_count)]
    if content.motion in _ROTATE_LEFT:
        return _rotate(base, -_shift(frame_index, segment_count))
    if content.motion in _BREATHE_MOTION:
        factor = _breathe_factor(frame_index)
        return [_scale(cell, factor) for cell in base]
    if content.motion in _TWINKLE_MOTION:
        return [_scale(cell, _twinkle_factor(frame_index, index)) for index, cell in enumerate(base)]
    return _rotate(base, _shift(frame_index, segment_count))


def _render_flat_style(style: str, palette: tuple[RGB, ...], segment_count: int, frame_index: int) -> Frame:
    if style == "fade":
        return [_palette_cycle_colour(palette, frame_index, smooth=True)] * segment_count
    if style == "jump":
        return [_palette_cycle_colour(palette, frame_index, smooth=False)] * segment_count
    if style == "twinkle":
        base = _palette_gradient(palette, segment_count)
        return [_scale(cell, _twinkle_factor(frame_index, index)) for index, cell in enumerate(base)]
    if style == "breathe":
        factor = _breathe_factor(frame_index)
        return [_scale(cell, factor) for cell in _palette_gradient(palette, segment_count)]
    if style == "marquee":
        return _rotate(_palette_tile(palette, segment_count), _shift(frame_index, segment_count))
    if style == "chase":
        lit = palette[0] if palette else _WHITE
        position = _shift(frame_index, segment_count) % segment_count
        return [lit if index == position else _OFF for index in range(segment_count)]
    return _rotate(_palette_gradient(palette, segment_count), _shift(frame_index, segment_count))


def _render_flat(content: FlatContent, segment_count: int, frame_index: int) -> Frame:
    style = _FLAT_STYLE.get(content.family, _DEFAULT_FLAT_STYLE)
    return _render_flat_style(style, content.palette, segment_count, frame_index)


def _render_combo(content: ComboContent, segment_count: int, frame_index: int) -> Frame:
    if not content.effects:
        return _rotate(_palette_gradient(content.palette, segment_count), _shift(frame_index, segment_count))
    phase_length = max(1, _LOOP_FRAMES // len(content.effects))
    active = min(frame_index // phase_length, len(content.effects) - 1)
    family = content.effects[active][0]
    style = _FLAT_STYLE.get(family, _DEFAULT_FLAT_STYLE)
    return _render_flat_style(style, content.palette, segment_count, frame_index - active * phase_length)


def _scene_palette(scene: SceneEntry) -> tuple[RGB, ...]:
    digest = hashlib.sha256(f"{scene.code}:{scene.param}".encode()).digest()
    return tuple(_hsv(digest[offset] / 255.0, 0.85, 1.0) for offset in (0, 8, 16, 24))


def _hsv(hue: float, saturation: float, value: float) -> RGB:
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return (_clamp_channel(red * 255), _clamp_channel(green * 255), _clamp_channel(blue * 255))


def _render_scene(scene: SceneEntry, segment_count: int, frame_index: int) -> Frame:
    return _rotate(_interpolate(_scene_palette(scene), segment_count), _shift(frame_index, segment_count))


def is_animated(look: PreviewLook) -> bool:
    """Whether the look plays a motion loop (as opposed to a single static frame)."""
    return isinstance(look, SketchContent | FlatContent | ComboContent | SceneEntry)


def frame_count(look: PreviewLook, *, reduce_motion: bool) -> int:
    return _LOOP_FRAMES if is_animated(look) and not reduce_motion else 1


def render(look: PreviewLook, segment_count: int, frame_index: int) -> Frame:
    """Pure per-frame render: the ``segment_count``-wide RGB row at ``frame_index`` (loops)."""
    match look:
        case SegmentContent():
            return _render_segments(look, segment_count)
        case VibrantContent():
            return _render_vibrant(look, segment_count)
        case SketchContent():
            return _render_sketch(look, segment_count, frame_index)
        case FlatContent():
            return _render_flat(look, segment_count, frame_index)
        case ComboContent():
            return _render_combo(look, segment_count, frame_index)
        case SceneEntry():
            return _render_scene(look, segment_count, frame_index)
        case UnknownContent():
            return [_OFF] * segment_count


def render_frames(look: PreviewLook, segment_count: int, *, reduce_motion: bool) -> FrameMatrix:
    """Assemble the preview matrix; reduce-motion collapses a loop to its mid-animation frame."""
    if reduce_motion:
        return [render(look, segment_count, _STILL_FRAME if is_animated(look) else 0)]
    return [render(look, segment_count, index) for index in range(frame_count(look, reduce_motion=False))]


@dataclass(frozen=True)
class PreviewImage:
    """An encoded preview: raw image bytes plus their HTTP content type."""

    content_type: str
    data: bytes


def _expand_frame(frame: Frame, width: int, height: int, cell_px: int) -> bytes:
    count = len(frame)
    row = bytearray()
    for pixel in range(width):
        red, green, blue = frame[min(pixel // cell_px, count - 1)]
        row += bytes((red, green, blue))
    return bytes(row) * height


def encode(matrix: FrameMatrix) -> PreviewImage:
    """Encode a frame matrix to a PNG still (one frame) or a looped GIF (many frames)."""
    from PIL import Image

    segment_count = len(matrix[0])
    width = max(1, segment_count * _CELL_PX)
    frames = [
        Image.frombytes("RGB", (width, _HEIGHT_PX), _expand_frame(frame, width, _HEIGHT_PX, _CELL_PX))
        for frame in matrix
    ]
    buffer = io.BytesIO()
    if len(frames) == 1:
        frames[0].save(buffer, format="PNG")
        return PreviewImage("image/png", buffer.getvalue())
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=_FRAME_DURATION_MS,
        disposal=2,
    )
    return PreviewImage("image/gif", buffer.getvalue())


def render_preview_image(look: PreviewLook, segment_count: int, reduce_motion: bool) -> PreviewImage:
    """Render and encode the currently-selected look (positional args for executor dispatch)."""
    return encode(render_frames(look, segment_count, reduce_motion=reduce_motion))


def _fingerprint(look: PreviewLook) -> dict[str, Any]:
    if isinstance(look, SceneEntry):
        return {"kind": "scene", "code": look.code, "param": look.param}
    return content_to_dict(look)


def look_hash(look: PreviewLook, segment_count: int) -> str:
    """Stable hash of everything that determines the rendered pixels (the cache ``palette_hash``)."""
    payload = json.dumps([segment_count, _fingerprint(look)], sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()[:16]
