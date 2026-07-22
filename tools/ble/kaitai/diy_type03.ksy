meta:
  id: diy_type03
  title: Govee H617A reassembled DIY "TYPE 0x03" body - Finger Sketch + Vibrant (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body for the shared DIY "TYPE 0x03" custom
  effect, used by both Finger Sketch and Vibrant on the H617A. The host reassembles
  the body by concatenating each 0xA3 frame's bytes[2:19] (17-byte chunks) in index
  order and closing at the empty idx=0xff terminator frame; the 0xA3 framing, the
  frame indices and the per-frame XOR are transport and are NOT modelled here. A
  reassembled body therefore carries NO checksum field.

  On-wire layout after reassembly (raw bytes, in order):
    01 <linecount> 03 <EFFECT> <SPEED> <BRIGHT> <bgR> <bgG> <bgB> <groupcount>
      [ <segcount> <fillR> <fillG> <fillB> <segindex x segcount> ]...  <zero padding>

  - 01           generic build_a3_multi body marker (raw).
  - linecount    A3 data-chunk count (transport, not a payload field). A single-data-
                 chunk body is padded to 17 bytes and closed by an appended empty
                 idx=0xff terminator frame, so it reassembles to 17 data + 17 zero
                 bytes = 34 bytes with linecount = 0x02 (every captured Sketch body).
                 A body that spills into more chunks uses the plain form (its last data
                 frame is the idx=0xff terminator, no empty frame): a 2-chunk Sketch
                 body is still linecount 0x02 / 34 bytes, the 15-segment Vibrant body is
                 linecount 0x05 / 85 bytes. linecount is never below 0x02 for this
                 family (the app never emits a lone frame; see build_a3_multi).
  - 03           the TYPE selector that routes the body to this grammar.
  - EFFECT       motion / effect code (enum below). Vibrant fixes it to 0x09.
  - SPEED,BRIGHT 0..100 percentage bytes (0x64 = 100).
  - bg RGB       background colour for unpainted segments. Vibrant fixes it to 01 01 01.
  - groupcount   number of distinct resolved-colour paint groups. Segments that share
                 a colour merge into one group listing all their 0-based indices, so
                 this counts colours, NOT segments and NOT gradient stops.
  - paint groups groupcount x { segcount, fill RGB, segcount 0-based segment indices }.
  - padding      transport zero-padding to the 17-byte A3 chunk boundary (and, for a
                 single-data-chunk body, the appended empty idx=0xff terminator frame);
                 grammar-enforced all-zero, consumed to EOF.

  Encoders in custom_components/ha_govee_led_ble/protocol.py are the write-side
  source of truth: build_sketch (~L268, terminator=True) and build_vibrant (~L309,
  terminator omitted) both emit exactly this body via build_a3_multi(0x03, ...).
  Re-verified byte-exact against captured Finger Sketch and Vibrant bodies; captures
  are ground truth. Other A3 bodies (scene rgbicv2 0x02, music 0x41, Flat/Combo
  0x04) use different grammars and must not be routed here.
seq:
  - id: header
    type: govee_common::a3_header
    doc: >
      offsets 0..1, the shared A3 reassembled-body header 01 <linecount>. linecount
      is the A3 data-chunk count (never below 0x02): build_a3_multi writes chunk_count,
      plus 1 when a trailing empty 0xff terminator frame is appended (the
      single-data-chunk form). [CONFIRMED_LIVE] linecount 0x02 in every captured Sketch
      body, 0x05 in the captured 15-segment Vibrant body.
  - id: body_type
    contents: [0x03]
    doc: >
      offset 2, raw 0x03 TYPE selector identifying the shared Finger Sketch / Vibrant
      DIY body. [CONFIRMED_LIVE] present in every body this spec round-trips.
  - id: effect
    type: u1
    enum: effect
    doc: >
      offset 3, motion / effect selector. [CONFIRMED_LIVE] all six codes captured in
      the 2026-07-16 Finger Sketch session with matching app action-log labels;
      Vibrant fixes this to clockwise (0x09).
  - id: speed
    type: u1
    doc: >
      offset 4, animation speed as a 0..100 percentage byte (0x64 = 100), per
      protocol.py _SKETCH_SPEED_RANGE. [CONFIRMED_LIVE] 0x00 / 0x33 / 0x5b / 0x64
      captured; Vibrant fixes this to 0x00.
  - id: brightness
    type: u1
    doc: >
      offset 5, brightness as a 0..100 percentage byte (0x64 = 100). [CONFIRMED_LIVE]
      0x32 / 0x64 captured; Vibrant fixes this to 0x64.
  - id: background
    type: govee_common::rgb
    doc: >
      offsets 6..8, background colour applied to unpainted segments, wire order R G B.
      [CONFIRMED_LIVE] ff/ff/ff, 00/00/ff and 00/3a/b7 captured (Sketch); Vibrant
      fixes this to 01/01/01.
  - id: group_count
    type: u1
    doc: >
      offset 9, number of distinct resolved-colour paint groups that follow. Counts
      colours, not segments and not gradient stops (segments sharing a colour merge
      into one group). [CONFIRMED_LIVE] 0x00 (motion set, nothing painted), 0x01
      (Sketch) and 0x0f (15-segment Vibrant) captured.
  - id: groups
    type: paint_group
    repeat: expr
    repeat-expr: group_count
    doc: >
      offset 10.., the paint groups, one per distinct colour, built by
      protocol.py _group_by_colour_0based. [CONFIRMED_LIVE] round-tripped with 0 and 1
      groups (Sketch) and 15 groups (Vibrant).
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: >
      transport zero-padding: build_a3_multi pads every 0xA3 chunk to 17 bytes and a
      single-data-chunk body is closed by an appended 17-byte empty 0xff terminator
      frame, so the reassembled body is zero-filled past the paint groups.
      Grammar-enforced all-zero, consumed to EOF. [CONFIRMED_LIVE] single-data-chunk
      Sketch bodies carry a full 17-byte empty terminator (>= 17 trailing zeros); a
      Sketch body that spills into a second A3 chunk still reassembles to 34 bytes but
      its final data frame is the terminator, leaving fewer trailing zeros; the
      exactly-85-byte 15-segment Vibrant body leaves this empty.
enums:
  effect:
    # Finger Sketch motion codes; names from the captured app action log
    # (2026-07-16) and protocol.py _SKETCH_MOTION_CODES (custom_effects.py L83-84).
    0x02: cycle
    0x09: clockwise
    0x0a: counter_clockwise
    0x0f: twinkle
    0x13: gradient
    0x14: breathe
types:
  paint_group:
    doc: |
      One resolved colour and every 0-based segment index painted with it. Emitted by
      protocol.build_sketch / build_vibrant via _group_by_colour_0based: colours are
      listed first-seen, and all segments resolving to the same colour are merged into
      a single group whose segcount is the number of indices that follow.
    seq:
      - id: seg_count
        type: u1
        doc: >
          number of 1-byte segment indices in this group, i.e. how many segments merge
          onto this colour. [CONFIRMED_LIVE] 0x01..0x04 captured (Sketch); 0x01 in
          every captured Vibrant group.
      - id: fill
        type: govee_common::rgb
        doc: >
          the resolved fill colour for this group, wire order R G B. [CONFIRMED_LIVE]
          e.g. ff/00/00 (Sketch red) and the gradient stop colours (Vibrant).
      - id: segment_indices
        type: u1
        repeat: expr
        repeat-expr: seg_count
        doc: >
          the 0-based segment indices painted with `fill`. [CONFIRMED_LIVE] both
          contiguous and sparse index sets captured, e.g. [0,1,2] and [0,1,2,4].
