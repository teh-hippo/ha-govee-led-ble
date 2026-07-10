"""Unit tests for the pure effect-preview renderer and its PNG/GIF encoder."""

import io

from PIL import Image

from custom_components.ha_govee_led_ble import preview as p
from custom_components.ha_govee_led_ble.custom_effects import (
    ComboContent,
    FlatContent,
    SegmentContent,
    SketchContent,
    UnknownContent,
    VibrantContent,
)
from custom_components.ha_govee_led_ble.protocol import _interpolate
from custom_components.ha_govee_led_ble.scenes import SceneEntry

_RED = (255, 0, 0)
_GREEN = (0, 255, 0)
_BLUE = (0, 0, 255)


def test_render_segments_static_pads_missing_with_off():
    look = SegmentContent(colors=(_RED, _GREEN, None))
    assert p.render(look, 4, 0) == [_RED, _GREEN, (0, 0, 0), (0, 0, 0)]
    # frame_index is ignored for a static look.
    assert p.render(look, 4, 7) == p.render(look, 4, 0)


def test_render_vibrant_matches_interpolate_parity():
    stops = ((0, 0, 0), (255, 255, 255))
    assert p.render(VibrantContent(stops=stops), 5, 0) == list(_interpolate(stops, 5))


def test_render_vibrant_empty_stops_is_off():
    assert p.render(VibrantContent(stops=()), 3, 0) == [(0, 0, 0)] * 3


def test_render_sketch_rotates_right_by_default():
    look = SketchContent(motion=0x09, background=(0, 0, 0), colors=(_RED, _GREEN, _BLUE, (9, 9, 9)))
    base = p.render(look, 4, 0)
    assert base == [_RED, _GREEN, _BLUE, (9, 9, 9)]
    # frame 3 => shift round(3*4/12)=1 to the right.
    assert p.render(look, 4, 3) == [(9, 9, 9), _RED, _GREEN, _BLUE]


def test_render_sketch_counter_clockwise_rotates_left():
    look = SketchContent(motion=0x0A, background=(0, 0, 0), colors=(_RED, _GREEN, _BLUE, (9, 9, 9)))
    assert p.render(look, 4, 3) == [_GREEN, _BLUE, (9, 9, 9), _RED]


def test_render_sketch_breathe_dims_uniformly():
    look = SketchContent(motion=0x14, background=(0, 0, 0), colors=(_RED, _RED, _RED, _RED))
    assert p.render(look, 4, 0) == [_RED] * 4  # factor 1.0 at frame 0
    mid = p.render(look, 4, 6)  # dimmest frame
    assert all(cell == mid[0] for cell in mid) and mid[0] < _RED


def test_render_sketch_twinkle_varies_per_segment():
    look = SketchContent(motion=0x0F, background=(0, 0, 0), colors=(_RED, _RED, _RED, _RED))
    frame = p.render(look, 4, 3)
    assert len(set(frame)) > 1  # per-segment phase produces different brightnesses


def test_render_flat_styles_cover_every_family():
    palette = (_RED, _GREEN, _BLUE)
    for family in (0x00, 0x01, 0x02, 0x03, 0x04, 0x08, 0x09, 0x0A, 0xFF):
        frame = p.render(FlatContent(family=family, palette=palette), 6, 3)
        assert len(frame) == 6
        assert all(isinstance(channel, int) and 0 <= channel <= 255 for cell in frame for channel in cell)


def test_render_flat_empty_palette_falls_back_to_white_gradient():
    assert p.render(FlatContent(family=0x09, palette=()), 3, 0) == [(255, 255, 255)] * 3


def test_render_flat_marquee_empty_palette_is_white():
    assert p.render(FlatContent(family=0x03, palette=()), 4, 3) == [(255, 255, 255)] * 4


def test_render_flat_fade_empty_palette_is_white():
    assert p.render(FlatContent(family=0x00, palette=()), 3, 2) == [(255, 255, 255)] * 3


def test_render_flat_jump_single_colour_holds_that_colour():
    assert p.render(FlatContent(family=0x01, palette=(_RED,)), 3, 5) == [_RED] * 3


def test_render_flat_chase_lights_single_cell():
    frame = p.render(FlatContent(family=0x08, palette=(_RED,)), 5, 0)
    assert frame.count(_RED) == 1 and frame.count((0, 0, 0)) == 4


def test_render_combo_cycles_and_handles_empty():
    combo = ComboContent(palette=(_RED, _GREEN), effects=((0x00, 0), (0x08, 0)))
    assert len(p.render(combo, 6, 0)) == 6
    assert len(p.render(combo, 6, 11)) == 6
    empty = ComboContent(palette=(_RED, _GREEN), effects=())
    assert len(p.render(empty, 6, 2)) == 6


def test_render_scene_is_deterministic_and_animated():
    scene = SceneEntry(code=42, param="abc")
    assert p.render(scene, 5, 0) == p.render(scene, 5, 0)
    assert p.is_animated(scene) is True
    # distinct scenes produce distinct palettes.
    assert p.render(scene, 5, 0) != p.render(SceneEntry(code=7, param="xyz"), 5, 0)


def test_render_unknown_is_off():
    assert p.render(UnknownContent(kind="mystery", raw={}), 3, 0) == [(0, 0, 0)] * 3


def test_static_looks_report_single_frame():
    for look in (SegmentContent(colors=(_RED,)), VibrantContent(stops=(_RED, _BLUE))):
        assert p.is_animated(look) is False
        assert p.frame_count(look, reduce_motion=False) == 1
        assert p.frame_count(look, reduce_motion=True) == 1


def test_reduce_motion_collapses_animation_to_one_frame():
    look = SketchContent(motion=0x09, colors=(_RED, _GREEN, _BLUE))
    off = p.render_frames(look, 3, reduce_motion=False)
    on = p.render_frames(look, 3, reduce_motion=True)
    assert len(off) == p._LOOP_FRAMES and len(off) > 1
    assert len(on) == 1
    assert on[0] == p.render(look, 3, p._STILL_FRAME)


def test_render_frames_static_is_single_frame_both_ways():
    look = SegmentContent(colors=(_RED, _GREEN))
    assert p.render_frames(look, 2, reduce_motion=False) == [p.render(look, 2, 0)]
    assert p.render_frames(look, 2, reduce_motion=True) == [p.render(look, 2, 0)]


def test_render_is_deterministic_across_calls():
    look = SketchContent(motion=0x09, colors=(_RED, _GREEN, _BLUE))
    assert p.render_frames(look, 3, reduce_motion=False) == p.render_frames(look, 3, reduce_motion=False)


def test_encode_single_frame_is_png_with_expected_size():
    image = p.render_preview_image(SegmentContent(colors=(_RED, _GREEN, _BLUE)), 3, True)
    assert image.content_type == "image/png"
    assert image.data[:4] == b"\x89PNG"
    with Image.open(io.BytesIO(image.data)) as decoded:
        assert decoded.format == "PNG"
        assert decoded.size == (3 * p._CELL_PX, p._HEIGHT_PX)


def test_encode_multi_frame_is_animated_gif():
    look = SketchContent(motion=0x0F, colors=tuple([_RED] * 15))
    matrix = p.render_frames(look, 15, reduce_motion=False)
    assert len(matrix) == p._LOOP_FRAMES
    image = p.render_preview_image(look, 15, False)
    assert image.content_type == "image/gif"
    assert image.data[:4] == b"GIF8"
    with Image.open(io.BytesIO(image.data)) as decoded:
        assert decoded.is_animated
        assert decoded.n_frames == p._LOOP_FRAMES


def test_look_hash_is_stable_and_sensitive():
    look = SegmentContent(colors=(_RED, _GREEN))
    assert p.look_hash(look, 3) == p.look_hash(look, 3)
    assert p.look_hash(look, 3) != p.look_hash(look, 4)  # segment count matters
    assert p.look_hash(look, 3) != p.look_hash(SegmentContent(colors=(_RED, _BLUE)), 3)  # colours matter


def test_look_hash_scene_uses_code_and_param():
    assert p.look_hash(SceneEntry(code=1, param="a"), 3) != p.look_hash(SceneEntry(code=2, param="a"), 3)
    assert p.look_hash(SceneEntry(code=1, param="a"), 3) == p.look_hash(SceneEntry(code=1, param="a"), 3)
