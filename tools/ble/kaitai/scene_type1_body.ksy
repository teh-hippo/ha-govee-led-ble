meta:
  id: scene_type1_body
  title: Govee H617A reassembled type-1 (legacy) scene body (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body for catalogue scene_type 1, the format
  scene_body.ksy deliberately fails closed on. On-wire layout:
    01 <linecount> 01 <config> <step_count> <step>... <palette_count> <rgb>... <zero padding>
  under the layout-0 config that every fixture carries; see the config field for layout 1.
  Only type 1 belongs here; type 2 (rgbicv2) is scene_body.ksy and type 0 has no
  body at all (those nine scenes ship an empty param and are activated by code
  alone, so nothing is uploaded).

  VENDOR NAME: scene_type 1 is the vendor's MULTI_V1_NEW_SCENES. The same grammar
  also arrives under commByte 7 (MULTI_V3_NEW_SCENES) on other SKUs, shipped as a
  catalogue scene rather than a user DIY; H617A never emits 7. See
  govee_common::a3_header for why these names must be quoted against the wire
  commByte and never against a class suffix.
  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.

  THE LAYOUT RESTS ON A CATALOGUE DIFFERENTIAL, NOT ON A CAPTURE. No type-1 scene on
  any SKU is adjustable, so no capture on any device can isolate these fields by moving
  a control, and waiting for one would wait forever. A catalogue differential is not a
  weaker substitute for a capture here, it is the only instrument that can reach these
  bytes. That is also why every structural field below is and cannot be
  promoted by device work.

  THE EVIDENCE THAT REMAINS IN-REPO. Two sources, both kept beside this spec. First,
  the captured Halloween 1173 upload, which is wire-true and pins one value per field.
  Second, eight type-1 catalogue params frozen from the keyless per-SKU
  light-effect-libraries endpoint (see fetch_effect_library.py), carried with the
  type-1 fixtures. Their whole job is breadth that no H617A param can supply: their
  palette_counts are 1, 2, 3, 4, 5, 6, 7 and 10.

  A LARGER CORPUS WAS REMOVED ON . A frozen 27-SKU third-party archive
  previously backed the numbers here and let three of these fields carry
  CONFIRMED_LIVE. It was retired along with the sweep that read it, and those fields
  were downgraded in the same change rather than left resting on prose. What it showed
  is recorded in the individual field docs as observed history, explicitly not as
  reproducible evidence. Re-closing these fields properly needs a fresh catalogue
  differential or a device with adjustable type-1 scenes.

  THE FIXED-SELECTOR ALTERNATIVE IS STILL FALSIFIED. The earlier draft offered a rival
  reading that consumed both H617A params just as exactly: a FIXED 0x04 selector
  followed by exactly four rgb, with the step's trailing pair as two independent u1
  fields. It fitted only because palette_count happened to be 4 in both scenes. Across
  the eight retained type-1 params that byte takes EIGHT different values (1, 2, 3, 4,
  5, 6, 7 and 10) and
    len(param) == 2 + 5*step_count + 1 + 3*palette_count
  holds for every one of them. A constant cannot take eight values, so the rival
  reading is dead and palette_count is a count. The 10 is cards_game, and it matters
  more than the others: it is the only value above 7, so it is the one that rules out
  a 3-bit field as well as a constant. This argument survived the corpus
  removal intact, because it never needed the corpus.

  BYTE 0 IS A LAYOUT DISCRIMINATOR, NOT A MARKER, AND IS NOW MODELLED AS ONE. It was
  once modelled as a fixed 0x83 "because that is all two identical samples can support",
  which stated a constant where the format has a field. The frozen scene_type == 1 sweep
  had already shown it is not fixed: it takes 0x03, 0x83, 0x93 and 0x95, and its value
  selects the record layout. 0x13 does NOT appear under the filter, so the earlier draft's
  0x13 group was type-2 record_count leakage, not a type-1 layout. Bit 0x80 is orthogonal
  to the layout: the 0x03 params and the 0x83 params both satisfy the same 5-byte-step
  arithmetic, so masking it off isolates the layout. The earlier draft's stronger claim
  that a scene ships byte-identical under 0x03 and 0x83 on different SKUs is NOT
  reproducible in this corpus, whose only 0x03 params are H6051 "Work" and "Rush" with
  no 0x83 twin, so treat it as unproven. The field is named config, decomposed into
  instances, and both layouts are grammar; see the config field for the bit assignment
  and for the one thing that still fails closed.

  WHAT REMAINS OPEN. step::value is the field no differential settled: its high byte is
  0x00 in all 102 step records of this layout and all 81 of the 8-byte 0x93 layout, so no
  catalogue can separate a u2le from two independent u1 bytes on values alone. The vendor
  read and write paths do separate them, and agree it is one 16-bit little-endian integer;
  that is recorded on the field. It still needs a device shipping a step value above 255
  before the byte order itself is observed rather than reasoned.

  THE ROUND-TRIP IS INTERNAL, NOT A CAPTURE. The fixtures frame the catalogue param
  with our own encoder and reassemble it with our own reader (see
  tests/test_protocol_wire_parity.py), so they prove self-consistency and exact
  consumption, not wire truth. The one genuine wire datum is below.

  CATALOGUE PARAM == BODY PAYLOAD HERE TOO. A captured
  Halloween application uploaded a 51-byte A3 body, which is the 3-byte A3/type
  prefix plus this 45-byte param plus 3 bytes of chunk padding, so the frozen param
  is the payload for type 1 exactly as it is for type 2 (see scene_body.ksy). This is
  what connects the catalogue differential above to the wire: it confirms that the
  bytes the differential segments are the bytes H617A actually receives. What the
  capture alone cannot show is where the field boundaries inside those bytes fall,
  and no capture on this hardware ever will, because nothing varies them.

  THE FORMAT LOOKS MODEL-INDEPENDENT. The two local catalogues corroborate
  at the byte level: H617A and H6199 ship byte-identical type-1 params (H617A 1173 /
  1170 against H6199 110 / 107). Cross-model generality beyond that pair was argued
  from the 27-SKU archive retired on  and is no longer reproducible in-repo,
  so it stays an inference. All of this is evidence about vendor catalogue data, never
  about H6199 device behaviour, which stays out of scope here.
seq:
  - id: header
    type: govee_common::a3_header
    doc: 'shared A3 body header 01 <linecount>'
  - id: scene_type
    type: u1
    valid:
      eq: 1
    doc: 'A3 body type byte (frame offset 2); guard fails the grammar closed on anything but type 1, mirroring scene_body.ksy which guards for type 2. Wire-true from the captured Halloween upload.'
  - id: config
    type: u1
    valid:
      expr: 'layout <= 1 and colour_stride == 3'
    doc: 'A PACKED CONFIG BYTE, named for what it is rather than for what a pair of identical samples made it look like. Bits 0-2 are the colour-component stride in bytes, bit 3 is ignored by the vendor splitters, bits 4-6 select the record layout, and bit 7 is orthogonal to the layout dispatch (the app labels it follow-system-brightness, which is a method name and not a wire fact, so the instance below is named for the bit). Every fixture we hold is 0x83, which is stride 3 layout 0. THE DECOMPOSITION IS LOAD-BEARING, NOT DECORATIVE: the instances below are consumed by this guard and by the steps switch, so a wrong bit assignment fails the parse instead of sitting beside it in prose. That is a weaker instrument than it sounds while every sample is 0x83, because some wrong assignments still yield stride 3 layout 0; only a body with a different config byte separates the bit positions outright, and crafting a 0x93 is the cheapest way to get one. THE GUARD FAILS CLOSED ON TWO DIFFERENT THINGS FOR TWO DIFFERENT REASONS. Layout 2 and above is rejected because the vendor rejects it outright, so there is nothing to model. Stride 4 and 5 are rejected although the vendor accepts them, because they are its RGBW and RGBWW colour widths: a property of hardware that has white channels, not of this body format. This spec is the H617A''s, the H617A is stride 3, and widening it from vendor code would be inferring another model''s behaviour, which is the one move this repo does not make. Layout is not the same kind of claim: it is a property of the body, and 0x93 and 0x95 were both seen in our own retired type-1 corpus, which is why both layouts are grammar here and only one of the strides is.'
  - id: step_count
    type: u1
    doc: 'the number of steps that follow. DOWNGRADED  from CONFIRMED_LIVE when the frozen cross-SKU corpus that carried it was removed from the repo: that tag rested on 37 catalogue params, and an analysis whose input is gone is prose, not evidence. What survives in-repo is the captured Halloween body, which pins this byte at 6 and consumes exactly, plus the eight catalogue params in the type-1 fixtures, whose step_counts are 1 and 2. Two live values cannot separate a count from a fixed field, and no type-1 scene on any SKU is adjustable, so no capture on this hardware can close it either. Closing it properly needs a fresh catalogue differential or a device with adjustable type-1 scenes. Both vendor splitters multiply it and use it as the slice bound, which is consistent with a count but is code rather than wire.'
  - id: steps
    type:
      switch-on: layout
      cases:
        0: step
        1: step_inline_colour
    repeat: expr
    repeat-expr: step_count
    doc: 'step_count fixed-width records whose width the config byte selects. DOWNGRADED  with step_count above: the width-1..16 solver that admitted 5 as the only fitting geometry ran over the frozen cross-SKU corpus, which is no longer in the repo. Width 5 still consumes the captured Halloween body and all eight type-1 fixtures with zero residue, so the layout-0 geometry is not in doubt for what we hold; what is gone is the breadth that made it the ONLY admissible width. The layout-1 branch is unexercised by every fixture we have and exists because the alternative was a paragraph of prose describing a record geometry, which is the one thing this repo keeps out of prose.'
  - id: palette_count
    type: u1
    if: layout == 0
    doc: 'the number of palette colours that follow, layout 0 only: layout 1 carries a colour inside every record and has no palette section at all, so the byte is absent rather than zero. DOWNGRADED  with the fields above when the frozen cross-SKU corpus left the repo. THE FALSIFICATION SURVIVES INTACT: the eight type-1 catalogue params kept alongside this spec take palette_count 1, 2, 3, 4, 5, 6, 7 and 10, each consuming exactly, and a constant cannot take eight values, so the rival reading of a fixed 0x04 selector stays dead. The 10 (cards_game) does the most work of the eight: being the only value above 7 it also rules out a 3-bit field. The tag drops to inferred not because the argument weakened but because its evidence is catalogue format rather than a device control being moved, and no type-1 scene on any SKU is adjustable, so no capture can promote it.'
  - id: palette
    type: govee_common::rgb
    repeat: expr
    repeat-expr: palette_count
    if: layout == 0
    doc: 'the effect palette, shared govee_common::rgb, palette_count entries. The length is variable, not fixed at four, and decodes to the colours the effects show: oranges for Halloween, pinks and purples for Sweet. Present only under layout 0, for the reason given on palette_count.'
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: 'transport zero padding to the A3 chunk boundary; grammar-enforced all-zero. Wire-true from the captured Halloween upload, which padded 48 body bytes to 51.'
instances:
  colour_stride:
    value: 'config & 0x07'
    doc: 'config bits 0-2: the width in bytes of one colour, which the vendor maps 3 to RGB, 4 to RGBW and 5 to RGBWW. Guarded to 3 on the config field, so this reads 3 in everything that parses; it is here because the guard and the layout-1 record both need to say WHICH quantity is pinned, and a magic 0x83 said nothing.'
  layout:
    value: '(config >> 4) & 0x07'
    doc: 'config bits 4-6: the record layout selector, and the switch the steps field dispatches on. 0 is fixed 5-byte steps with one shared palette after them; 1 is per-record colour and no palette section. Bit 3 sits between the two instances and is read by neither vendor splitter, so it is deliberately not modelled: an instance for it would name a bit nothing consumes.'
  brightness_flag:
    value: '(config & 0x80) != 0'
    doc: 'config bit 7, named for the bit rather than for the app method that sets it, because what is established numerically is only that no layout dispatch consults it. It is what makes 0x03 and 0x83 the same layout. Nothing in this grammar reads it, which is the honest state of the evidence: it is decoded so a fixture can pin it, not because we know what it does.'
types:
  step:
    doc: |
      One 5-byte animation step: a colour and a 16-bit value. Halloween's six steps
      are #fff500 then five near-whites, each with value 5 except the last at 6;
      Sweet's single step is #ffb4ff with value 50. Both layouts use this record
      unchanged; layout 1 appends a colour to it rather than replacing it.
    seq:
      - id: colour
        type: govee_common::rgb
        doc: 'the step colour, shared govee_common::rgb'
      - id: value
        type: u2
        doc: '16-bit little-endian value at step offset 3; 5,5,5,5,5,6 across Halloween and 50 for Sweet, so it varies and is a real field. Duration or speed is the obvious reading and is NOT established, because no type-1 scene on any SKU is adjustable, so no control anywhere can be moved against it. THE SPLIT AMBIGUITY IS UNRESOLVED ON THE WIRE: the high byte is 0x00 in every step record we hold, so two independent u1 bytes fit those bytes identically, and only a device shipping a step value above 255 can decide it by observation. What has changed is that the reading is no longer chosen by analogy alone. The vendor takes bytes 0,1,2 as three separate unsigned bytes and bytes 3..4 as ONE 2-byte integer, on both the read and the write path, and its 2-byte helper writes the low byte first; so the encoder that produces these params treats this as u2le. That is code, not wire, so the tag stays inferred. It agrees with the analogy that chose it: every other multi-byte field in this family is little-endian (see status_reply::cm_scene.scene_id), and contrast status_reply::unit_count_body, which is modelled as two bytes precisely because its 16-bit reading would have to be big-endian.'
  step_inline_colour:
    doc: |
      One layout-1 record: the same 5-byte step above, followed by one inline colour of
      colour_stride bytes, which is 3 here because the config guard pins the stride.
      Layout 1 has no shared palette; the colour that layout 0 looks up in the palette
      section travels inside every record instead. The vendor slices exactly this way,
      taking five bytes as a step param and then stride bytes which it feeds to the
      palette colour parser with a synthetic count of one.

      NO FIXTURE EXERCISES THIS BRANCH. Every type-1 body we hold is layout 0. It is
      modelled rather than rejected because the geometry is fully determined and the only
      other place to put it was a prose paragraph, which is what this repo refuses to do
      with wire structure. Treat a parse through here as unverified until a real 0x93
      body is captured or crafted; that is also what would promote the config field.
    seq:
      - id: param
        type: step
        doc: 'the same 5-byte step record layout 0 uses, reused unchanged'
      - id: colour
        type: govee_common::rgb
        doc: 'the per-record colour, shared govee_common::rgb because the config guard pins colour_stride to 3; a stride 4 or 5 body would carry one or two further channel bytes here and is failed closed on the config field rather than modelled'
