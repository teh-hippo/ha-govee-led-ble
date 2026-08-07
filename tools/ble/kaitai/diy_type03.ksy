meta:
  id: diy_type03
  title: Govee H617A reassembled DIY "TYPE 0x03" body - Finger Sketch + Vibrant (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body for the shared DIY "TYPE 0x03" custom
  effect, used by both Finger Sketch and Vibrant on the H617A.

  VENDOR NAME: TYPE 0x03 is the vendor's MULTI_V1_NEW_DIY_GRAFFITI, and its
  "graffiti" really is the freehand-paint surface we call Finger Sketch - established
  by walking the vendor grammar over catalogue bodies, not by the word. See
  govee_common::a3_header for why such names must be quoted against the wire commByte.

  The 0xA3 framing,
  the frame indices and the per-frame XOR are transport and are NOT modelled here;
  the reassembly rule lives once on govee_common::a3_header and MUST be read before
  decoding a capture, because this family exercises both framing forms. A
  reassembled body therefore carries NO checksum field.

  APP SURFACES. Three surfaces produce this body:
    * Finger Sketch is a DIY editor and has NO Save control at all, only Effect /
      Speed / Brightness / colour. Every write is a live preview.
    * Vibrant is NOT under DIY. It is the third tab of Color mode
      (Whole / Subsection / Vibrant).
    * Share Space (the "Apply DIY effects shared by other users" gallery) REPLAYS
      this body. Both shared effects sampled  uploaded TYPE 0x03 and
      activated slot 0xfe. This matters twice over: it is the only producer that is
      neither a live editor nor locally authored, and it is what falsified the
      old "activation byte tracks the body type" reading (see
      govee_common::diy_selector.type_byte).
  The first two write a fixed activation slot rather than a library id -- Sketch
  0x20, Vibrant 0x84 -- see govee_common::diy_selector for the slot semantics.

  VIBRANT'S BODY SHAPE. Editing the Vibrant colour set
  uploads an 85-byte body (linecount 5) and activates it with 33 05 0a 84 03. Where a
  Sketch body merges same-coloured segments into few groups, Vibrant emits ONE GROUP
  PER SEGMENT: group_count 0x0f, then fifteen groups of seg_count 1 carrying a
  generated ramp across indices 0..14. Removing blue from an orange/yellow/blue set
  produced ff7f00 stepping to ffff00, matching the on-screen preview bar. Consumption
  is exact at 10 + 15*5 = 85 with zero excess, so the same grammar covers both
  producers without special-casing.

  SHARED BODIES USE THE FULL GRAMMAR. Foreign bodies
  exercise variable group sizes, which neither local editor does: a "northern lights"
  share decoded as EFFECT 0x13 SPEED 0x45 BRIGHT 0x64 bg ffffff, group_count 7 with
  seg_counts 2,2,2,1,3,2,3 covering all fifteen segments, consumed exactly at 53
  bytes. A second share used seg_count 2 throughout over only fourteen segments
  (indices 0..13), so the segment span is NOT required to cover the strip and a
  shared body may have been authored on a differently sized device.

  On-wire layout after reassembly (raw bytes, in order):
    01 <linecount> 03 <EFFECT> <SPEED> <BRIGHT> <bgR> <bgG> <bgB> <groupcount>
      [ <segcount> <fillR> <fillG> <fillB> <segindex x segcount> ]...  <zero padding>

  - 01           generic build_a3_multi body marker (raw).
  - linecount    A3 chunk count (transport, not a payload field); semantics on
                 govee_common::a3_header. Observed here: every captured Sketch body
                 is linecount 0x02 / 34 bytes (single data chunk plus the appended
                 empty frame, and a Sketch body that spills into a second chunk still
                 lands on 34), and the 15-segment Vibrant body is linecount 0x05 /
                 85 bytes in the plain form. Never below 0x02 for this family.
  - 03           the TYPE selector that routes the body to this grammar.
  - EFFECT       motion / effect code (enum below). Vibrant fixes it to 0x09.
  - SPEED,BRIGHT 0..100 percentage bytes (0x64 = 100).
  - bg RGB       background colour for unpainted segments. Vibrant fixes it to 01 01 01.
  - groupcount   number of distinct resolved-colour paint groups. Segments that share
                 a colour merge into one group listing all their 0-based indices, so
                 this counts colours, NOT segments and NOT gradient stops.
  - paint groups groupcount x { segcount, fill RGB, segcount 0-based segment indices }.
  - padding      transport zero-padding to the 17-byte A3 chunk boundary (and, for a
                 single-data-chunk body, the appended empty 0xff frame);
                 grammar-enforced all-zero, consumed to EOF.

  Encoders in custom_components/ha_govee_led_ble/protocol.py are the write-side
  source of truth: build_sketch and build_vibrant both emit exactly this body via
  build_a3_multi(0x03, ...), and NEITHER passes terminator, so both take the default
  of False. This doc previously distinguished them as "build_sketch (terminator=True)
  and build_vibrant (terminator omitted)"; that distinction no longer exists. Sketch
  was originally pinned on a body that fitted in one chunk, where build_a3_multi
  forces a terminator whatever the flag says and the flag is therefore unfalsifiable.
  A two-chunk Finger Sketch capture on  settled the framing and the explicit
  argument went away. Both were re-verified byte-exact against fresh captures on
  , build_vibrant including its gamma-2.2 gradient interpolation; captures
  are ground truth. Other A3 bodies (scene rgbicv2 0x02, music 0x41, Flat/Combo 0x04)
  use different grammars and must not be routed here.

  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
seq:
  - id: header
    type: govee_common::a3_header
    doc: >
      offsets 0..1, the shared A3 reassembled-body header 01 <linecount>.
      linecount 0x02 in every captured Sketch body, 0x05 in the
      captured 15-segment Vibrant body.
  - id: body_type
    contents: [0x03]
    doc: >
      offset 2, raw 0x03 TYPE selector identifying the shared Finger Sketch / Vibrant
      DIY body. present in every body this spec round-trips.
  - id: effect
    type: u1
    enum: effect
    doc: >
      offset 3, motion / effect selector. all six codes captured in
      the  Finger Sketch session with matching app action-log labels;
      Vibrant fixes this to clockwise (0x09).
  - id: speed
    type: u1
    doc: >
      offset 4, animation speed as a 0..100 percentage byte (0x64 = 100), per
      protocol.py _SKETCH_SPEED_RANGE. 0x00 / 0x33 / 0x5b / 0x64
      captured; Vibrant fixes this to 0x00.
  - id: brightness
    type: u1
    doc: >
      offset 5, brightness as a 0..100 percentage byte (0x64 = 100).
      0x32 / 0x64 captured; Vibrant fixes this to 0x64.
  - id: background
    type: govee_common::rgb
    doc: >
      offsets 6..8, background colour applied to unpainted segments, wire order R G B.
      ff/ff/ff, 00/00/ff and 00/3a/b7 captured (Sketch); Vibrant
      fixes this to 01/01/01.
  - id: group_count
    type: u1
    doc: >
      offset 9, number of distinct resolved-colour paint groups that follow. Counts
      colours, not segments and not gradient stops (segments sharing a colour merge
      into one group). 0x00 (motion set, nothing painted), 0x01
      (Sketch) and 0x0f (15-segment Vibrant) captured.
  - id: groups
    type: paint_group
    repeat: expr
    repeat-expr: group_count
    doc: >
      offset 10.., the paint groups, one per distinct colour, built by
      protocol.py _group_by_colour_0based. round-tripped with 0 and 1
      groups (Sketch) and 15 groups (Vibrant).
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: >
      transport zero-padding: build_a3_multi pads every 0xA3 chunk to 17 bytes and a
      single-data-chunk body is closed by an appended all-zero 0xff-indexed frame,
      so the reassembled body is zero-filled past the paint groups.
      Grammar-enforced all-zero, consumed to EOF. single-data-chunk
      Sketch bodies carry that full 17-byte empty frame (>= 17 trailing zeros); a
      Sketch body that spills into a second A3 chunk still reassembles to 34 bytes
      but has no appended frame (its last DATA chunk is the one indexed 0xff),
      leaving fewer trailing zeros; the exactly-85-byte 15-segment Vibrant body
      leaves this empty.
enums:
  effect:
    # Finger Sketch motion codes; names from the captured app action log
    # () and protocol.py _SKETCH_MOTION_CODES (custom_effects.py).
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
          onto this colour. 0x01..0x04 captured (Sketch); 0x01 in
          every captured Vibrant group.
      - id: fill
        type: govee_common::rgb
        doc: >
          the resolved fill colour for this group, wire order R G B.
          e.g. ff/00/00 (Sketch red) and the gradient stop colours (Vibrant).
      - id: segment_indices
        type: u1
        repeat: expr
        repeat-expr: seg_count
        doc: >
          the 0-based segment indices painted with `fill`. both
          contiguous and sparse index sets captured, e.g. [0,1,2] and [0,1,2,4].
