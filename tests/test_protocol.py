"""Unit tests for the Govee BLE protocol module."""

import base64

import pytest

from custom_components.ha_govee_led_ble import protocol as proto
from custom_components.ha_govee_led_ble.custom_effects import (
    ComboContent,
    EffectValidationError,
    FlatContent,
    SegmentContent,
    SketchContent,
    UnknownContent,
    VibrantContent,
)

H = bytes.fromhex

# CAT §2.2 editor default palette (seven colours): FF0000 FF7D00 FFFF00 00FF00 0000FF 00FFFF 8B00FF.
_DEFAULT_PALETTE = (
    (0xFF, 0, 0),
    (0xFF, 0x7D, 0),
    (0xFF, 0xFF, 0),
    (0, 0xFF, 0),
    (0, 0, 0xFF),
    (0, 0xFF, 0xFF),
    (0x8B, 0, 0xFF),
)


def _valid(pkt):
    assert len(pkt) == 20 and proto.xor_checksum(pkt[:19]) == pkt[19]


def test_xor_checksum():
    assert proto.xor_checksum(bytes(19)) == 0x00
    assert proto.xor_checksum(bytearray([0x33, 0x01, 0x01] + [0x00] * 16)) == 0x33
    assert proto.xor_checksum(bytearray([0x33, 0x01, 0x00] + [0x00] * 16)) == 0x32
    assert proto.xor_checksum(bytearray([0xAA, 0x01] + [0x00] * 17)) == 0xAB


def test_split_status_frame_valid_20_byte():
    frame = bytearray([0xAA, 0x05] + [0x01] * 17)
    frame.append(proto.xor_checksum(frame))
    assert len(frame) == 20
    result = proto.split_status_frame(bytes(frame))
    assert result == (0x05, bytes(frame[2:19]))
    _domain, payload = result
    assert len(payload) == 17  # checksum byte dropped


def test_split_status_frame_short_loose_keeps_tail():
    frame = bytes([0xAA, 0x04, 0x4B, 0x00, 0x00, 0x00, 0x00, 0x00])
    assert proto.split_status_frame(frame) == (0x04, frame[2:])


def test_split_status_frame_bad_checksum_keeps_fallback():
    body = bytes([0xAA, 0x05] + [0x01] * 17)
    frame = body + bytes([proto.xor_checksum(body) ^ 0x01])
    assert len(frame) == 20
    domain, payload = proto.split_status_frame(frame)
    assert domain == 0x05
    assert payload == frame[2:]  # checksum not stripped when it fails to verify
    assert len(payload) == 18


def test_split_status_frame_rejects_non_status_and_short():
    assert proto.split_status_frame(bytes([0x33, 0x05, 0x01])) is None
    assert proto.split_status_frame(bytes([0xAA, 0x05])) is None
    assert proto.split_status_frame(b"") is None


def test_packet_basics():
    _valid(proto.build_packet(0x33, 0x01, [0x01]))
    assert proto.build_packet(0x33, 0x01, [0x01]) == H("3301010000000000000000000000000000000033")
    pkt = proto.build_packet(0x33, 0x01, [])
    assert all(pkt[i] == 0x00 for i in range(2, 19))
    assert len(proto.build_packet(0x33, 0x01, list(range(20)))) == 20


@pytest.mark.parametrize(
    "on,h", [(True, "3301010000000000000000000000000000000033"), (False, "3301000000000000000000000000000000000032")]
)
def test_power(on, h):
    pkt = proto.build_power(on)
    assert pkt == H(h) and len(pkt) == 20


@pytest.mark.parametrize("val,exp", [(100, 100), (0, 0), (200, 100), (-10, 0)])
def test_brightness(val, exp):
    pkt = proto.build_brightness(val)
    assert pkt[0:2] == bytes([0x33, 0x04]) and pkt[2] == exp
    _valid(pkt)


@pytest.mark.parametrize("val,raw", [(0, 0), (50, 50), (100, 100), (120, 100), (-1, 0)])
def test_white_brightness(val, raw):
    pkt = proto.build_white_brightness(val)
    assert pkt[0:7] == bytes([0x33, 0x05, 0x15, 0x02, raw, 0xFF, 0x7F])  # all-segments mask 0x7fff
    _valid(pkt)


def test_color():
    pkt = proto.build_color_rgb(255, 0, 0)
    assert pkt[:14] == bytes([0x33, 0x05, 0x15, 0x01, 0xFF, 0, 0, 0, 0, 0, 0, 0, 0xFF, 0x7F])
    assert len(pkt) == 20
    assert tuple(proto.build_color_rgb(300, -10, 128)[4:7]) == (255, 0, 128)
    # colour temp is a true-white KELVIN frame: 33 05 15 01 00 00 00 <Khi Klo> <R G B> ... FF 7F
    pkt = proto.build_color_temp(4000)
    assert pkt[:7] == bytes([0x33, 0x05, 0x15, 0x01, 0, 0, 0])
    assert (pkt[7] << 8) | pkt[8] == 4000 and (pkt[12], pkt[13]) == (0xFF, 0x7F)
    assert (pkt[9], pkt[10], pkt[11]) == proto.kelvin_to_rgb(4000)
    assert proto.build_color_temp(1000)[7:9] == bytes([0x07, 0xD0])  # clamped to 2000K
    assert proto.build_color_temp(12000)[7:9] == bytes([0x23, 0x28])  # clamped to 9000K


def test_segments_to_mask():
    assert proto.segments_to_mask([1]) == 0x0001  # segment k -> bit k-1
    assert proto.segments_to_mask([3]) == 0x0004
    assert proto.segments_to_mask([1, 2, 3]) == 0x0007
    assert proto.segments_to_mask([15]) == 0x4000
    assert proto.segments_to_mask([1, 1]) == 0x0001  # duplicates collapse
    assert proto.segments_to_mask(range(1, 16)) == 0x7FFF == proto.ALL_SEGMENTS_MASK
    assert proto.segments_to_mask(proto.ALL_SEGMENTS) == proto.ALL_SEGMENTS_MASK
    for bad in ([], [0], [16], [-1], [1, 16]):
        with pytest.raises(ValueError):
            proto.segments_to_mask(bad)


def test_segment_color():
    pkt = proto.build_segment_color([3], 10, 20, 30)  # mask 0x0004 at bytes[12:14]
    assert pkt[:14] == bytes([0x33, 0x05, 0x15, 0x01, 10, 20, 30, 0, 0, 0, 0, 0, 0x04, 0x00])
    _valid(pkt)
    assert proto.build_segment_color([1, 5, 9], 1, 2, 3)[12:14] == bytes([0x11, 0x01])  # mask 0x0111
    assert tuple(proto.build_segment_color([1], 300, -10, 128)[4:7]) == (255, 0, 128)  # channels clamp
    with pytest.raises(ValueError):
        proto.build_segment_color([], 1, 2, 3)
    with pytest.raises(ValueError):
        proto.build_segment_color([16], 1, 2, 3)


def test_segment_brightness():
    pkt = proto.build_segment_brightness([15], 50)  # mask 0x4000 at bytes[5:7]
    assert pkt[:7] == bytes([0x33, 0x05, 0x15, 0x02, 50, 0x00, 0x40])
    _valid(pkt)
    assert proto.build_segment_brightness([1], 200)[4] == 100  # pct clamps
    with pytest.raises(ValueError):
        proto.build_segment_brightness([], 50)


def test_segment_paint():
    assert proto.build_segment_paint([([1, 2], (255, 0, 0))]) == [H("33051501ff0000000000000003000000000000de")]
    pkts = proto.build_segment_paint([([1, 2], (255, 0, 0)), ([3], (0, 0, 255))])
    assert pkts == [proto.build_segment_color([1, 2], 255, 0, 0), proto.build_segment_color([3], 0, 0, 255)]
    rainbow = [([k], (k * 10, 0, 0)) for k in range(1, 16)]  # 15 distinct colours -> 15 packets
    assert len(proto.build_segment_paint(rainbow)) == 15


def test_all_segments_delegation_is_byte_identical():
    # Refactored wrappers must match the pre-refactor hardcoded bytes exactly (no wire change).
    assert proto.build_color_rgb(10, 20, 30) == H("330515010a141e0000000000ff7f0000000000a2")
    assert proto.build_white_brightness(50) == H("3305150232ff7f00000000000000000000000093")
    assert proto.build_color_rgb(1, 2, 3) == proto.build_segment_color(range(1, 16), 1, 2, 3)
    assert proto.build_white_brightness(75) == proto.build_segment_brightness(range(1, 16), 75)


@pytest.mark.parametrize(
    "kelvin,check",
    [
        (1000, lambda r, g, b: r == 255 and g > 0),
        (2700, lambda r, g, b: r == 255 and g > 100 and b < g),
        (5500, lambda r, g, b: r == 255 and g > 200 and b > 200),
        (6500, lambda r, g, b: r == 255 and b > 200),
        (10000, lambda r, g, b: b > 200),
        (500, lambda r, g, b: 0 <= r <= 255),
        (20000, lambda r, g, b: 0 <= r <= 255),
    ],
)
def test_kelvin_to_rgb(kelvin, check):
    r, g, b = proto.kelvin_to_rgb(kelvin)
    assert check(r, g, b), f"Failed at {kelvin}K: ({r},{g},{b})"


def test_kelvin_output_range():
    for k in range(1000, 10001, 500):
        assert all(0 <= c <= 255 for c in proto.kelvin_to_rgb(k)), f"Out of range at {k}K"


def test_scene():
    assert proto.build_scene(0x00) == H("3305040000000000000000000000000000000032")
    assert proto.build_scene(0x01) == H("3305040100000000000000000000000000000033")
    assert proto.build_scene(0x04) == H("3305040400000000000000000000000000000036")
    assert proto.build_scene(0x16) == H("3305041600000000000000000000000000000024")
    assert proto.build_scene(0x08) == H("330504080000000000000000000000000000003a")
    assert proto.build_scene(0x0A) == H("3305040a00000000000000000000000000000038")
    assert proto.build_scene(0x10) == H("3305041000000000000000000000000000000022")
    # Scene id is always 2 bytes little-endian (a small id keeps an explicit 0x00 high byte).
    assert proto.build_scene(0x05)[2:5] == bytes([0x04, 0x05, 0x00])
    assert proto.build_scene(10565)[2:5] == bytes([0x04, 0x45, 0x29])


def test_scene_multi():
    pkt = proto.build_scene(2163)
    assert (pkt[2], pkt[3], pkt[4]) == (0x04, 0x73, 0x08)
    _valid(pkt)
    assert proto.build_scene_multi("", 22) == [proto.build_scene(22)]
    pkts = proto.build_scene_multi(base64.b64encode(bytes(20)).decode(), 100)
    assert len(pkts) > 1
    for p in pkts:
        _valid(p)
    assert pkts[0][0:2] == bytes([0xA3, 0x00])
    assert pkts[0][4] == 0x02  # default scene_type body prefix
    assert proto.build_scene_multi(base64.b64encode(bytes(20)).decode(), 100, 1)[0][4] == 0x01
    assert pkts[-2][0:2] == bytes([0xA3, 0xFF])
    assert pkts[-1][0:3] == bytes([0x33, 0x05, 0x04])
    forest = (
        "AyYAAQAKAgH/GQG0CgoCyBQF//8AAP//////AP//lP8AFAGWAAAAACMAAg8F"
        "AgH/FAH7AAAB+goEBP8AtP8AR///4/8AAAAAAAAAABoAAAABAgH/BQHIFBQC"
        "7hQBAP8AAAAAAAAAAA=="
    )
    pkts = proto.build_scene_multi(forest, 2163)
    assert len(pkts) > 2
    for p in pkts:
        _valid(p)
    assert (pkts[0][0], pkts[0][2]) == (0xA3, 0x01)
    assert (pkts[-1][3], pkts[-1][4]) == (0x73, 0x08)


def test_build_h6199_scene_matches_current_ios_captures():
    aurora_a = "AiAAAAABAgH/MgEAAAAA+jIDAP8AAP//qv8AAwCAAAAAACMAAAADAgH/GQD6AAAC+gAEf/8A//8AoP//AP//FAH6AAD/AA=="
    assert proto.build_h6199_scene("", 0, 0) == [H("3305040000010000000000000000000000000033")]
    assert proto.build_h6199_scene(aurora_a, 215, 2) == [
        H("a3000105020220000000010201ff320100000049"),
        H("a30100fa320300ff0000ffffaaff000300800040"),
        H("a30200000023000000030201ff1900fa0000029c"),
        H("a303fa00047fff00ffff00a0ffff00ffff14016b"),
        H("a3fffa0000ff0000000000000000000000000059"),
        H("330504d7000200000000000000000000000000e7"),
    ]


def test_build_a3_multi():
    frames = proto.build_a3_multi(0x02, bytes(20))
    assert frames == [
        H("a3000102020000000000000000000000000000a2"),
        H("a3ff00000000000000000000000000000000005c"),
    ]
    for f in frames:
        _valid(f)
    # A single-chunk body is still framed as a numbered data frame + an empty 0xFF terminator
    # (linecount 0x02), never a lone frame; this is the form flat DIY uses for 1-3 colour palettes.
    single = proto.build_a3_multi(0x04, H("010064038b00ff"))
    assert single == [
        H("a300010204010064038b00ff00000000000000b6"),
        H("a3ff00000000000000000000000000000000005c"),
    ]
    for f in single:
        _valid(f)
    # build_scene_multi stays byte-identical: shared fragmenter + the 33 05 04 activate frame.
    b64 = base64.b64encode(bytes(range(40))).decode()
    assert proto.build_scene_multi(b64, 2205) == [*proto.build_a3_multi(2, bytes(range(40))), proto.build_scene(2205)]


def test_build_diy_activate():
    # H617A §3 "DIY select" 33 05 0a <slot>; slot 0xF0 observed (carries no colour).
    assert proto.build_diy_activate(0xF0) == H("33050af0000000000000000000000000000000cc")
    assert proto.build_diy_activate(0xBE)[:4] == H("33050abe")
    _valid(proto.build_diy_activate(0xF0))


def test_interpolate_linear_gradient():
    assert proto._interpolate((), 0) == []
    assert proto._interpolate(((10, 20, 30),), 3) == [(10, 20, 30), (10, 20, 30), (10, 20, 30)]
    assert proto._interpolate(((0, 0, 0), (255, 255, 255)), 1) == [(0, 0, 0)]
    assert proto._interpolate(((0, 0, 0), (255, 255, 255)), 3) == [(0, 0, 0), (128, 128, 128), (255, 255, 255)]
    three = proto._interpolate(((0, 0, 0), (100, 100, 100), (200, 200, 200)), 5)
    assert three == [(0, 0, 0), (50, 50, 50), (100, 100, 100), (150, 150, 150), (200, 200, 200)]


def test_build_segment_content_matches_captured_frames():
    # Tier 1 reuses the validated live write-path; byte-identical to captured colour/brightness frames.
    single = SegmentContent(colors=(None, None, (10, 20, 30)))  # paints segment 3 only
    assert proto.build_segment_content(single, segment_count=15) == [H("330515010a141e00000000000400000000000026")]
    whole = SegmentContent(colors=((10, 20, 30),) * 15)  # one colour group over the whole strip
    assert proto.build_segment_content(whole, segment_count=15) == [H("330515010a141e0000000000ff7f0000000000a2")]
    # distinct colours -> one frame each, first-seen order; None leaves a segment untouched
    two = SegmentContent(colors=((255, 0, 0), (255, 0, 0), None, (0, 0, 255)))
    assert proto.build_segment_content(two, segment_count=15) == [
        proto.build_segment_color([1, 2], 255, 0, 0),
        proto.build_segment_color([4], 0, 0, 255),
    ]
    # optional per-segment brightness groups append after the colour frames
    lit = SegmentContent(colors=(None, (1, 2, 3)), brightness=(None, 50))
    assert proto.build_segment_content(lit, segment_count=15) == [
        proto.build_segment_color([2], 1, 2, 3),
        H("3305150232020000000000000000000000000011"),
    ]
    for frame in proto.build_segment_content(lit, segment_count=15):
        _valid(frame)


def test_build_sketch_matches_live_capture():
    # Finger Sketch live H617A 3.02.24 (2026-07-16): Clockwise, bg white, 3 red segments 0,1,2.
    content = SketchContent(
        motion=0x09,
        speed=0x33,
        brightness=0x64,
        background=(255, 255, 255),
        colors=((255, 0, 0), (255, 0, 0), (255, 0, 0)),
    )
    frames = proto.build_sketch(content, segment_count=15)
    assert frames == [
        H("a300010203093364ffffff0103ff0000000102fc"),  # 01 <count 2> 03 EFFECT SPEED BRIGHT <bg> <groups>
        H("a3ff00000000000000000000000000000000005c"),  # empty 0xFF terminator frame
        H("33050a200300000000000000000000000000001f"),  # activation 33 05 0a <slot 0x20> <type 0x03>
    ]
    for frame in frames:
        _valid(frame)


def test_build_sketch_matches_catalogue():
    # CAT §2.4: Clockwise, background blue, one green group over segments 0,1,2,4 (0-based).
    content = SketchContent(
        motion=0x09,
        speed=0x33,
        brightness=0x64,
        background=(0, 0, 255),
        colors=((0, 255, 0), (0, 255, 0), (0, 255, 0), None, (0, 255, 0)),
    )
    body = H("0933640000ff010400ff0000010204")  # EFFECT SPEED BRIGHT <bg> <groups> <segcount fill segidx...>
    frames = proto.build_sketch(content, segment_count=15)
    # Composition through the shared fragmenter: terminated A3 stream then slot/type activation.
    assert frames == [*proto.build_a3_multi(0x03, body, terminator=True), proto.build_diy_activate(0x20, 0x03)]
    assert frames[-1] == H("33050a200300000000000000000000000000001f")  # activation 33 05 0a 20 03
    for frame in frames:
        _valid(frame)


def test_build_vibrant_matches_live_capture():
    # VALIDATED live H617A 3.02.24 (2026-07-20): Vibrant is a TYPE 0x03 gradient sharing the Finger
    # Sketch grammar. Stops interpolate per channel in gamma-2.2 linear light to the captured 15
    # fills; body is motion/speed/brightness/bg + 15 single-segment groups; activation 33 05 0a 84 03.
    content = VibrantContent(stops=((255, 127, 0), (255, 255, 0), (0, 255, 0)))
    body = H(
        "0900640101010f"  # motion 09, speed 00, brightness 64, bg 01 01 01, group count 0f
        "01ff7f000001ff9a000101ffb0000201ffc3000301ffd4000401ffe3000501fff2000601ffff0007"
        "01eeff000801dbff000901c6ff000a01adff000b0190ff000c0169ff000d0100ff000e"
    )
    frames = proto.build_vibrant(content, segment_count=15)
    assert frames == [*proto.build_a3_multi(0x03, body), proto.build_diy_activate(0x84, 0x03)]
    # on-wire preamble 01 <linecount> 03: a complete 15-entry body is five A3 chunks, so linecount 0x05.
    assert frames[0][2:5] == H("010503")
    assert frames[-1] == H("33050a84030000000000000000000000000000bb")
    for frame in frames:
        _valid(frame)


def test_build_flat_diy_matches_catalogue():
    # CAT §2.2: Jumping1, seven-colour default palette, default speed 0x32.
    content = FlatContent(family=0x01, variant=0x00, speed=0x32, palette=_DEFAULT_PALETTE)
    body = H("01003215ff0000ff7d00ffff0000ff000000ff00ffff8b00ff")  # FAMILY VARIANT SPEED PLEN <7 colours>
    frames = proto.build_flat_diy(content)
    assert frames == [*proto.build_a3_multi(0x04, body), proto.build_diy_activate(0xF0)]
    assert frames[-1] == H("33050af0000000000000000000000000000000cc")
    for frame in frames:
        _valid(frame)


def test_build_flat_diy_single_chunk_live():
    # Live H617A: a 1-3 colour flat body fits one A3 chunk, yet the app always sends a numbered
    # data frame + an empty 0xFF terminator (linecount 0x02), never a lone frame. Byte-pinned to
    # captures h617a-diy-jumping1-a (Jumping1, one colour 8B00FF) and diy-crossing (Crossing,
    # three colours); the activation slot is app-assigned (0xF0 default here).
    jumping1 = FlatContent(family=0x01, variant=0x00, speed=0x64, palette=((0x8B, 0x00, 0xFF),))
    assert proto.build_flat_diy(jumping1) == [
        H("a300010204010064038b00ff00000000000000b6"),
        H("a3ff00000000000000000000000000000000005c"),
        H("33050af0000000000000000000000000000000cc"),
    ]
    crossing = FlatContent(
        family=0x0A, variant=0x00, speed=0x64, palette=((0xFF, 0, 0), (0xFF, 0x7D, 0), (0xFF, 0xFF, 0))
    )
    assert proto.build_flat_diy(crossing) == [
        H("a3000102040a006409ff0000ff7d00ffff0000be"),
        H("a3ff00000000000000000000000000000000005c"),
        H("33050af0000000000000000000000000000000cc"),
    ]
    for frame in proto.build_flat_diy(jumping1) + proto.build_flat_diy(crossing):
        _valid(frame)


def test_build_combo_matches_catalogue():
    # CAT §2.5: Fade1 (00,00) + Marquee1 (03,03), shared seven-colour palette; seqlen = 2*count = 0x04.
    content = ComboContent(variant=0x00, speed=0x32, palette=_DEFAULT_PALETTE, effects=((0x00, 0x00), (0x03, 0x03)))
    # FF <var> <speed> is not pinned by CAT (defaults shown); the tail from PLEN onward is the worked example.
    body = H("ff003215ff0000ff7d00ffff0000ff000000ff00ffff8b00ff0400000303")
    frames = proto.build_combo(content)
    assert frames == [*proto.build_a3_multi(0x04, body), proto.build_diy_activate(0xF0)]
    # CAT worked example ends 04 00 00 03 03 00 on the wire: seqlen, both pairs, then one a3 zero-pad byte.
    assert frames[-2][13:19] == H("040000030300")
    assert frames[-1] == H("33050af0000000000000000000000000000000cc")
    for frame in frames:
        _valid(frame)


def test_build_combo_matches_current_ios_capture():
    content = ComboContent(
        speed=0x33,
        palette=((255, 0, 0),),
        effects=((0x00, 0x00), (0x01, 0x00), (0x03, 0x03), (0x08, 0x09)),
    )
    body = H("ff003303ff0000080000010003030809")
    frames = proto.build_combo(content, slot=0xEF)
    assert frames == [*proto.build_a3_multi(0x04, body), H("33050aef000000000000000000000000000000d3")]
    for frame in frames:
        _valid(frame)


def test_build_combo_matches_direct_f0_probe():
    content = ComboContent(
        speed=0x33,
        palette=((255, 0, 0), (0, 0, 255)),
        effects=((0x00, 0x00), (0x03, 0x03)),
    )
    assert proto.build_combo(content) == [
        H("a300010204ff003306ff00000000ff0400000369"),
        H("a3ff03000000000000000000000000000000005f"),
        H("33050af0000000000000000000000000000000cc"),
    ]


def test_build_custom_effect_dispatches_each_kind():
    seg = SegmentContent(colors=(None, None, (10, 20, 30)))
    assert proto.build_custom_effect(seg, segment_count=15) == [H("330515010a141e00000000000400000000000026")]
    sketch = SketchContent(colors=((0, 255, 0),))
    assert proto.build_custom_effect(sketch, segment_count=15) == proto.build_sketch(sketch, segment_count=15)
    vibrant = VibrantContent(stops=((255, 0, 0), (0, 0, 255)))
    assert proto.build_custom_effect(vibrant, segment_count=15) == proto.build_vibrant(vibrant, segment_count=15)
    flat = FlatContent(family=0x01, variant=0x00, palette=((0xFF, 0, 0),))
    assert proto.build_custom_effect(flat, segment_count=15) == proto.build_flat_diy(flat)
    combo = ComboContent(palette=((0xFF, 0, 0),), effects=((0x00, 0x00),))
    assert proto.build_custom_effect(combo, segment_count=15) == proto.build_combo(combo)
    with pytest.raises(proto.EffectValidationError):
        proto.build_custom_effect(UnknownContent(kind="mystery", raw={}), segment_count=15)


def test_constants():
    assert proto.STATE_QUERY == H("AA010000000000000000000000000000000000AB")
    assert proto.BRIGHTNESS_QUERY == H("AA040000000000000000000000000000000000AE")
    assert proto.COLOR_MODE_QUERY == H("AA050000000000000000000000000000000000AF")
    assert proto.FW_QUERY == H("AA060000000000000000000000000000000000AC")
    assert proto.HW_QUERY == H("AA070300000000000000000000000000000000AE")
    assert proto.KEEP_ALIVE == proto.STATE_QUERY
    assert (proto.COMMAND_HEADER, proto.STATUS_HEADER) == (0x33, 0xAA)
    assert (proto.POWER_PACKET_TYPE, proto.BRIGHTNESS_PACKET_TYPE, proto.COLOR_PACKET_TYPE) == (0x01, 0x04, 0x05)
    assert (proto.FIRMWARE_PACKET_TYPE, proto.HARDWARE_PACKET_TYPE) == (0x06, 0x07)
    assert (proto.COLOR_MODE_SCENE, proto.COLOR_MODE_VIDEO, proto.COLOR_MODE_MUSIC, proto.COLOR_MODE_STATIC) == (
        0x04,
        0x00,
        0x13,
        0x15,
    )


def test_firmware_hardware_version_decode():
    # H617A/H6199 current-app handshakes return ASCII, NUL-padded versions.
    fw_reply = H("aa06332e30322e3234000000000000000000009b")
    hw_reply = H("aa0703332e30312e30310000000000000000009d")
    h6199_hw_reply = H("aa0703332e30322e30310000000000000000009e")
    fw_domain, fw_payload = proto.split_status_frame(fw_reply)
    hw_domain, hw_payload = proto.split_status_frame(hw_reply)
    assert (fw_domain, hw_domain) == (0x06, 0x07)
    assert proto.parse_fw_version(fw_payload) == "3.02.24"
    assert proto.parse_hw_version(hw_payload) == "3.01.01"
    assert proto.parse_hw_version(proto.split_status_frame(h6199_hw_reply)[1]) == "3.02.01"
    # NUL padding is trimmed; an empty payload decodes to None.
    assert proto.parse_fw_version(b"3.02.24\x00\x00") == "3.02.24"
    assert proto.parse_hw_version(b"") is None
    assert proto.parse_hw_version(b"\x02" + b"3.01.01") is None


def test_video_mode():
    def chk(kw, idx, exp):
        pkt = proto.build_video_mode(**kw)
        assert (tuple(pkt[idx]) if isinstance(idx, slice) else pkt[idx]) == exp
        _valid(pkt)

    # iOS always sends the full 8-byte frame: 33 05 00 <region> <mode> <sat> <sound> <softness>.
    chk({}, slice(0, 8), (0x33, 0x05, 0x00, 0x01, 0x00, 100, 0x00, 100))
    assert proto.build_video_mode() == H("3305000100640064000000000000000000000037")
    chk(dict(full_screen=False, game_mode=True, saturation=75), slice(3, 6), (0x00, 0x01, 75))
    chk(dict(sound_effects=True, sound_effects_softness=50), slice(6, 8), (0x01, 50))
    # Sound off still carries softness (it persists); default softness is 0x64.
    assert proto.build_video_mode(sound_effects=False, sound_effects_softness=100) == H(
        "3305000100640064000000000000000000000037"
    )
    chk(dict(sound_effects=False, sound_effects_softness=1), slice(6, 8), (0x00, 0x01))
    chk(dict(saturation=200), 5, 100)
    chk(dict(saturation=-5), 5, 0)
    chk(dict(sound_effects=True, sound_effects_softness=200), 7, 100)
    chk(dict(sound_effects=True, sound_effects_softness=-5), 7, 1)
    chk(dict(sound_effects=False, sound_effects_softness=-5), 7, 1)  # floor 0x01 applies with sound off too
    chk(
        dict(full_screen=False, game_mode=True, saturation=60, sound_effects=True, sound_effects_softness=75),
        slice(2, 8),
        (0x00, 0x00, 0x01, 60, 0x01, 75),
    )
    # Live H6199 iOS capture (h6199-video-controls-batch.pcap): sound off yet softness 0x64 retained,
    # and the softness minimum is 0x01 (never 0).
    assert proto.build_video_mode(
        full_screen=False, game_mode=False, saturation=0x13, sound_effects=False, sound_effects_softness=0x64
    ) == H("3305000000130064000000000000000000000041")
    assert proto.build_video_mode(
        full_screen=False, game_mode=False, saturation=0x13, sound_effects=True, sound_effects_softness=0x01
    ) == H("3305000000130101000000000000000000000025")


def test_video_white_balance():
    assert proto.build_video_white_balance(0x07, 0x0A) == H("33a9000301070a00000000000000000000000095")
    assert proto.build_video_white_balance(0x0F, 0x04) == H("33a90003010f0400000000000000000000000093")
    assert proto.build_video_white_balance(-1, 999) == proto.build_video_white_balance(0, 255)
    _valid(proto.build_video_white_balance(0x10, 0x05))


def test_music_mode():
    def chk(mode, kw, idx, exp):
        pkt = proto.build_music_mode_with_color(mode, **kw)
        assert (tuple(pkt[idx]) if isinstance(idx, slice) else pkt[idx]) == exp
        _valid(pkt)

    chk(0x05, dict(sensitivity=80), slice(0, 6), (0x33, 0x05, 0x13, 0x05, 80, 0x00))
    chk(0x04, dict(sensitivity=100, color=(255, 0, 128)), slice(6, 10), (0x01, 255, 0, 128))
    chk(0x03, dict(sensitivity=150), 4, 99)
    chk(0x03, dict(sensitivity=80, calm=True), 5, 0x01)
    chk(0x03, dict(sensitivity=50, calm=True, color=(128, 64, 32)), slice(5, 10), (0x01, 0x01, 128, 64, 32))


def test_music_mode_style_count_per_mode():
    # byte5 = STYLE (Dynamic 0 / Calm 1); byte6 = COUNT (0 = auto-colour on, 1 + RGB = manual colour).
    # Rhythm frames are the captured references (music mode-set 33 05 13, see
    # tools/ble/kaitai/music_body.ksy): `13 03 63 00 00` (Dynamic) and `13 03 63 01 01 0000ff` (Calm, blue).
    # Spectrum/Rolling send STYLE 0 and choose colour via COUNT (auto-colour = COUNT 0), per the
    # 2026-07-08 live music-mode notes.
    bm = proto.build_music_mode_with_color
    # Rhythm 0x03 — byte5 = Dynamic(0) / Calm(1)
    assert bm(0x03, sensitivity=99) == H("3305130363000000000000000000000000000045")
    assert bm(0x03, sensitivity=99, color=(0, 0, 255), calm=True) == H("330513036301010000ff000000000000000000ba")
    # Spectrum 0x04 — auto-colour on = COUNT 0 (no RGB); manual colour = COUNT 1 + RGB
    assert bm(0x04, sensitivity=99) == H("3305130463000000000000000000000000000042")
    assert bm(0x04, sensitivity=99, color=(255, 0, 128)) == H("33051304630001ff00800000000000000000003c")
    # Rolling 0x06 — same COUNT semantics
    assert bm(0x06, sensitivity=99) == H("3305130663000000000000000000000000000040")
    assert bm(0x06, sensitivity=99, color=(10, 20, 30)) == H("330513066300010a141e00000000000000000041")
    for pkt in (bm(0x04), bm(0x06, color=(10, 20, 30))):
        _valid(pkt)


# Music per-mode movement params (§2.3, EXPERIMENTAL). Every expected frame below is replayed
# byte-exact from validate-20260709-122350.pcap + validation-report-20260709-123428.json; assembling
# the a3 fragments (dropping each frame's `a3 <idx>` prefix and trailing XOR) must reproduce it. Each
# (mode, overrides) pins a captured A/B/A transition — the same transitions that pinned the offsets.
_MUSIC_PARAM_FRAMES: dict[tuple[int, tuple[tuple[int, int], ...]], str] = {
    # Bloom 0x30: current iOS Dynamic / Calm A/B/A.
    (0x30, ()): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a50000000000000",
    (
        0x30,
        ((27, 0x14),),
    ): "0102413007ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0a14000000000000",
    # Shiny 0x31: current iOS Dynamic / Calm A/B/A.
    (0x31, ()): "0102413105ff0000ff7f00ffff0000ff000000ff05640a0000000000000000000000",
    (
        0x31,
        ((20, 0x14), (21, 0x46)),
    ): "0102413105ff0000ff7f00ffff0000ff000000ff14460a0000000000000000000000",
    # Separation 0x32: report music-p-gradient (build{}) / music-p-seppoint ([20]=5).
    (0x32, ()): "0102413205ff7f00ff0000ffff000000ff00ff0001015e0000000000000000000000",
    (0x32, ((20, 0x05),)): "0102413205ff7f00ff0000ffff000000ff00ff0005015e0000000000000000000000",
    # Hopping 0x33 (3-fragment): report music-p-relbright (build{}) / pcap relbright=0 ([29]=0).
    (0x33, ()): (
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000032620103020600000000000000000000000000000000"
    ),
    (0x33, ((29, 0x00),)): (
        "0103413307ff0000ff7f00ffff0000ff000000ff00ffff8b00ffff000000620103020600000000000000000000000000000000"
    ),
    # Piano 0x34: report music-p-keys (key count 15).
    (0x34, ()): "0102413407ff0000ff7f00ffff0000ff000000ff00ffff8b00ff000f0a0407000000",
    # Fountain 0x35: current Clockwise, Two-way and retained Counterclockwise captures.
    (0x35, ()): "0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0001055000000000",
    (
        0x35,
        ((26, 0x01), (28, 0x03)),
    ): "0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0101035000000000",
    (
        0x35,
        ((26, 0x02), (28, 0x05)),
    ): "0102413507ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0201055000000000",
    # Day & Night 0x37: pcap baseline (build{}), report music-p-segments ([26]=7) / music-p-speed ([27]=0x32).
    (0x37, ()): "0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff010a000000000000",
    (0x37, ((26, 0x07),)): "0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff070a000000000000",
    (0x37, ((27, 0x32),)): "0102413707ff0000ff7f00ffff0000ff000000ff00ffff8b00ff0132000000000000",
}


def _assemble_a3(packets):
    for pkt in packets:
        _valid(pkt)
    return b"".join(pkt[2:19] for pkt in packets)


def test_build_music_params_a3_reproduces_captured_bodies():
    for (mode, overrides), frame in _MUSIC_PARAM_FRAMES.items():
        assert _assemble_a3(proto.build_music_params_a3(mode, dict(overrides))) == H(frame)


def test_build_music_params_a3_flips_only_its_offset():
    # Overwriting one decoded offset changes exactly that byte; the rest of the captured body is verbatim.
    cases = (
        (0x30, 27, 0x14),
        (0x31, 20, 0x14),
        (0x31, 21, 0x46),
        (0x32, 20, 5),
        (0x32, 21, 0),
        (0x33, 29, 0),
        (0x34, 27, 8),
        (0x35, 26, 1),
        (0x35, 28, 3),
        (0x37, 26, 7),
        (0x37, 27, 50),
    )
    for mode, offset, value in cases:
        base = _assemble_a3(proto.build_music_params_a3(mode, {}))
        changed = _assemble_a3(proto.build_music_params_a3(mode, {offset: value}))
        assert [i for i in range(len(base)) if base[i] != changed[i]] == [offset]
        assert changed[offset] == value


def test_build_music_params_a3_never_writes_volatile_bytes():
    for mode, offset in ((0x32, 22), (0x34, 30)):
        with pytest.raises(ValueError, match="volatile"):
            proto.build_music_params_a3(mode, {offset: 0x01})


def test_build_music_params_a3_palette_guard_and_overlay():
    # A palette whose length differs from the captured colour count is rejected so offsets never shift.
    with pytest.raises(EffectValidationError):
        proto.build_music_params_a3(0x32, {}, palette=[(1, 2, 3)])
    # A correctly-sized palette overwrites only the RGB region, leaving the params/tail verbatim.
    palette = [(1, 2, 3)] * proto._MUSIC_PARAM_COUNT[0x32]
    assembled = _assemble_a3(proto.build_music_params_a3(0x32, {}, palette=palette))
    assert assembled[5:20] == bytes([1, 2, 3] * 5) and assembled[20] == 0x01


def test_parse():
    scene = proto.parse_color_mode_response(bytes([0x04, 0x9D, 0x08]))
    assert scene.mode is proto.ParsedMode.SCENE and scene.effect == "candy"
    p = proto.parse_color_mode_response(bytes([0x00, 0x00, 0x01, 42, 0x01, 55]))
    assert p.mode is proto.ParsedMode.VIDEO and p.video_mode == "game" and p.effect is None and not p.video_full_screen
    assert (p.video_saturation, p.video_sound_effects, p.video_sound_effects_softness) == (42, True, 55)
    p = proto.parse_color_mode_response(bytes([0x13, 0x04, 77, 0x00, 0x01, 1, 2, 3]))
    assert (
        p.mode is proto.ParsedMode.MUSIC
        and p.music_mode == "spectrum"
        and p.effect is None
        and p.music_sensitivity == 77
        and p.music_calm is None
        and p.music_color == (1, 2, 3)
    )
    p = proto.parse_color_mode_response(bytes([0x13, 0x03, 88, 0x01, 0x00]))
    assert p.music_mode == "rhythm" and p.effect is None and p.music_sensitivity == 88 and p.music_calm is True
    static = proto.parse_color_mode_response(bytes([0x15, 0x01, 10, 20, 30]))
    assert static.mode is proto.ParsedMode.COLOUR and static.rgb_color == (10, 20, 30)
    assert proto.parse_color_mode_response(bytes([0x15, 0x02, 50])).white_brightness == 50
    with pytest.raises(ValueError):
        proto.parse_color_mode_response(b"")


def test_parse_direct_diy_slot_readback():
    domain, payload = proto.split_status_frame(H("aa050af000000000000000000000000000000055"))
    parsed = proto.parse_color_mode_response(payload)
    assert domain == 0x05
    assert parsed.mode is proto.ParsedMode.DIY
    assert parsed.diy_slot == proto.DEFAULT_DIY_SLOT


def test_parse_music_calm_only_for_rhythm():
    # byte5 (payload index 3) is Dynamic/Calm only for Rhythm; Spectrum/Rolling repurpose it as the
    # auto-colour flag, so it must not bleed into music_calm (which set_music_mode inherits for Rhythm).
    parse = proto.parse_color_mode_response
    assert parse(bytes([0x13, 0x03, 60, 0x01, 0x00])).music_calm is True
    assert parse(bytes([0x13, 0x03, 60, 0x00, 0x00])).music_calm is False
    for mid, name in ((0x04, "spectrum"), (0x06, "rolling")):
        p = parse(bytes([0x13, mid, 60, 0x01, 0x00]))
        assert p.music_mode == name and p.effect is None and p.music_calm is None


def test_parse_padded_scene_and_unknown_mode():
    assert proto.parse_color_mode_response(bytes([0x04, 0x9D, 0x08, 0x00, 0x00])).effect == "candy"
    assert proto.parse_color_mode_response(bytes([0x99, 0x01, 0x02])) == proto.ParsedColorModeResponse()


W = proto.Weekday


def test_timer_repeat():
    # Mon=bit0 .. Sun=bit6; empty = one-time (0x80), every weekday = every day (0x00), else 0x80|mask.
    assert proto.timer_repeat() == proto.TIMER_REPEAT_ONCE == 0x80  # fire once
    assert proto.timer_repeat([W.TUE]) == 0x82  # Tue-only
    assert proto.timer_repeat([W.MON, W.TUE]) == 0x83  # Mon+Tue
    assert proto.timer_repeat([W.MON]) == 0x81
    assert proto.timer_repeat([W.SUN]) == 0xC0  # 0x80 | (1 << 6)
    assert proto.timer_repeat(list(W)) == 0x00  # every day (app sends 0x00, not 0xff)
    assert proto.timer_repeat([W.TUE, W.TUE]) == 0x82  # duplicates collapse
    for bad in ([7], [-1]):
        with pytest.raises(ValueError):
            proto.timer_repeat(bad)


def test_parse_timer_repeat():
    assert proto.parse_timer_repeat(0x80) == frozenset()  # one-time
    assert proto.parse_timer_repeat(0x82) == frozenset({W.TUE})
    assert proto.parse_timer_repeat(H("82")[0]) == frozenset({W.TUE})  # raw repeat byte 0x82 -> Tue
    assert proto.parse_timer_repeat(0x83) == frozenset({W.MON, W.TUE})
    assert proto.parse_timer_repeat(0x00) == frozenset(W)  # every day (app's canonical form)
    assert proto.parse_timer_repeat(0xFF) == frozenset(W)  # tolerated alias -> re-encodes to 0x00
    for byte in (0x00, 0x80, 0x81, 0x82, 0x83, 0xC0):
        assert proto.timer_repeat(proto.parse_timer_repeat(byte)) == byte  # round-trip


def test_timer_schedule():
    # slot0 enabled+on 06:00 one-time (spec cross-check 33 23 00 81 06 00 80).
    assert proto.build_timer_schedule(0, True, True, 6, 0, []) == H("3323008106008000000000000000000000000017")
    assert proto.build_timer_schedule(0, True, True, 6, 0, [W.TUE]) == H("3323008106008200000000000000000000000015")
    assert proto.build_timer_schedule(1, True, False, 22, 30, [W.MON, W.TUE]) == H(
        "33230180161e830000000000000000000000001a"
    )
    assert proto.build_timer_schedule(3, True, True, 7, 15, list(W)) == H("33230381070f000000000000000000000000009a")
    assert proto.build_timer_schedule(2, False, False, 0, 0, []) == H("3323020000008000000000000000000000000092")
    clamp = proto.build_timer_schedule(0, True, True, 25, 61, [])  # hour/minute clamp to 23/59
    assert (clamp[4], clamp[5]) == (23, 59)
    _valid(clamp)
    for bad in (-1, 4, 9):
        with pytest.raises(ValueError):
            proto.build_timer_schedule(bad, True, True, 6, 0, [])


def test_timer_sleep():
    assert proto.build_timer_sleep(True, 50, 30) == H("331101321e00000000000000000000000000000f")
    # enable=1, startBri clamps 5->10, closeMin=200, curMin=7.
    assert proto.build_timer_sleep(True, 5, 200, 7) == H("3311010ac80700000000000000000000000000e6")
    assert proto.build_timer_sleep(False, 150, 300)[2:6] == bytes([0, 100, 255, 0])  # enable/bri/close clamp
    _valid(proto.build_timer_sleep(True, 50, 30))


def test_timer_wakeup():
    # enable=1, endBri=80, 07:30, repeat Mon-Fri (0x9f), duration=20.
    assert proto.build_timer_wakeup(True, 80, 7, 30, [W.MON, W.TUE, W.WED, W.THU, W.FRI], 20) == H(
        "33120150071e9f140000000000000000000000e2"
    )
    # endBri 5->10, hour 25->23, minute 61->59, repeat one-time (0x80), duration 100->60.
    assert proto.build_timer_wakeup(True, 5, 25, 61, [], 100) == H("3312010a173b803c0000000000000000000000ba")
    assert proto.build_timer_wakeup(True, 50, 6, 0)[7] == 10  # duration default clamps up to 10
    _valid(proto.build_timer_wakeup(True, 80, 7, 30, [W.SAT, W.SUN], 30))


def test_poweroff_memory():
    assert proto.build_poweroff_memory(True) == H("3341010000000000000000000000000000000073")
    assert proto.build_poweroff_memory(False) == H("3341000000000000000000000000000000000072")


def test_parse_timer_schedule():
    p = proto.parse_timer_schedule(bytes([0x81, 6, 0, 0x80]))
    assert (p.enabled, p.on_action, p.hour, p.minute, p.repeat_days) == (True, True, 6, 0, frozenset())
    p = proto.parse_timer_schedule(bytes([0x80, 22, 30, 0x83]))
    assert (p.enabled, p.on_action, p.repeat_days) == (True, False, frozenset({W.MON, W.TUE}))
    assert proto.parse_timer_schedule(bytes([0x00, 0, 0, 0x80])).enabled is False
    with pytest.raises(ValueError):
        proto.parse_timer_schedule(bytes([0x81, 6, 0]))


def test_parse_timer_schedule_table():
    # Real aa 23 reply captured live: 0xff prefix + four 4-byte slot records.
    slots = proto.parse_timer_schedule_table(bytes.fromhex("ff800c17c0810910808100008081000080"))
    assert len(slots) == 4
    assert (slots[0].enabled, slots[0].on_action, slots[0].hour, slots[0].minute) == (True, False, 12, 23)
    assert (slots[1].enabled, slots[1].on_action, slots[1].hour, slots[1].minute) == (True, True, 9, 16)
    assert all(s.enabled for s in slots)
    # tolerates a body without the 0xff prefix
    assert len(proto.parse_timer_schedule_table(bytes.fromhex("810600808100008081000080810000ff"))) == 4


def test_parse_timer_sleep_and_wakeup():
    s = proto.parse_timer_sleep(bytes([1, 50, 30, 7]))
    assert (s.enabled, s.start_brightness, s.close_minutes, s.current_minutes) == (True, 50, 30, 7)
    assert proto.parse_timer_sleep(bytes([0, 10, 5])).current_minutes == 0  # curMin optional
    with pytest.raises(ValueError):
        proto.parse_timer_sleep(bytes([1, 50]))
    w = proto.parse_timer_wakeup(bytes([1, 80, 7, 30, 0x9F, 20]))
    assert (w.enabled, w.end_brightness, w.hour, w.minute, w.duration_minutes) == (True, 80, 7, 30, 20)
    assert w.repeat_days == frozenset({W.MON, W.TUE, W.WED, W.THU, W.FRI})
    with pytest.raises(ValueError):
        proto.parse_timer_wakeup(bytes([1, 80, 7, 30, 0x9F]))


def test_parse_poweroff_memory():
    p = proto.parse_poweroff_memory(bytes([1, 2]))
    assert (p.enabled, p.mode) == (True, 2)
    assert proto.parse_poweroff_memory(bytes([0])) == proto.ParsedPowerOffMemory(enabled=False, mode=None)
    with pytest.raises(ValueError):
        proto.parse_poweroff_memory(b"")
