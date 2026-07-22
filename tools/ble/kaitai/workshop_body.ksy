meta:
  id: workshop_body
  title: Govee H617A reassembled Workshop layer-container body (A3 TYPE 0x02, decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame Workshop body (host concatenates each frame's
  bytes[2:19]; the frame checksum/terminator is transport, not modelled here).
  Workshop is identified by A3 TYPE 0x02 plus the activation 33 05 04 91 01 02.
  On-wire layout:
    01 <linecount> 02 <layer_count> [<record_len> <layer_record>]... <zero padding>
  The leading "01 <linecount> 02" is the generic build_a3_multi transport header
  ([0x01, chunk_count, type_byte]); linecount is the 17-byte chunk count and varies
  with body length (02 one layer, 04 two, 09 five). The reassembled body length is
  always a whole number of 17-byte chunks, so linecount == len / 17.
  Each layer is a length-prefixed record; the remainder after the records is
  transport zero padding to the 17-byte A3 chunk boundary, outside the records.
  Re-verified against captured Workshop bodies (Christmas 5-layer, the select-type
  matrix, colour-family, brightness, movement and priority differentials); captures
  are ground truth. This is a DECODE-ONLY structural spec and models no write side.

  Evidence tags on every seq field are exactly one of:
    [CONFIRMED_LIVE] proven byte-exact by a round-tripped capture;
    [INFERRED]       reasoned from analysis, value/meaning not directly isolated;
    [INHERITED]      modelled from docs/write-side, no capture confirms it.
seq:
  - id: header
    type: govee_common::a3_header
    doc: >
      [CONFIRMED_LIVE] shared A3 body header 01 <linecount>. linecount is the 17-byte
      data-chunk count and equals len/17 (02 for one layer, 03/04 for larger, 09 for
      the five-layer Christmas body); the body is zero-padded to whole 17-byte chunks.
  - id: a3_type
    contents: [0x02]
    doc: '[CONFIRMED_LIVE] A3 TYPE 0x02; Workshop is always type 0x02 (raw).'
  - id: layer_count
    type: u1
    doc: '[CONFIRMED_LIVE] number of length-prefixed layer records that follow (1/2/5 seen).'
  - id: layers
    type: layer_record
    repeat: expr
    repeat-expr: layer_count
    doc: '[CONFIRMED_LIVE] layer_count length-prefixed records, emitted in creation order.'
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: '[CONFIRMED_LIVE] transport zero padding to the 17-byte A3 chunk boundary; grammar-enforced all-zero.'
enums:
  select_type:
    0x00: segment
    0x01: select_ic_continuously
    0x02: select_ic_randomly
    0x03: customize_segment
types:
  layer_record:
    doc: |
      One Workshop layer: a 1-byte length then that many record bytes. The record
      length grows only with the colour count M (record_len == 23 + 3*M), which the
      captures confirm byte-exact for M = 1, 2 and 3.
    seq:
      - id: record_len
        type: u1
        doc: '[CONFIRMED_LIVE] r0: number of record bytes that follow this length byte (0x1a M=1, 0x1d M=2, 0x20 M=3).'
      - id: body
        type: record_body
        size: record_len
        doc: '[CONFIRMED_LIVE] the record body, constrained to record_len bytes.'
  record_body:
    doc: |
      Workshop layer-record internals. Offsets count the record length byte as r0,
      so the first field here is r1. The 16-byte fixed prefix (r1..r16) is followed
      by the M-colour palette (r17..), then the selected-area and overall movement
      sub-blocks and finally the priority byte. r5/r6/r9 are present on the wire but
      their meaning is not isolated by the current captures.
    seq:
      - id: applied_area
        -orig-id: r1
        type: u1
        doc: >
          [CONFIRMED_LIVE] r1 Applied Area window: high nibble = width in tenths,
          low nibble = start in tenths (0x00 = whole strip). The five Christmas
          layers tile as 20 22 24 26 28 (width 2 at starts 0/2/4/6/8); 0x40 seen for
          a [0,4]-tenths window. This byte is the r1-tiling proof.
      - id: select_type
        -orig-id: r2
        type: u1
        enum: select_type
        doc: >
          [CONFIRMED_LIVE] r2 Select Type: 00 Segment, 01 Select IC Continuously,
          02 Select IC Randomly, 03 Customize Segment. All four seen on the wire with
          the documented r3:r4 parameter pairs.
      - id: select_param_1
        -orig-id: r3
        type: u1
        doc: >
          [CONFIRMED_LIVE] r3 Select-Type parameter 1 (meaning depends on r2):
          Segment 00, Continuously 00, Randomly 0f (max ICs), Customize 01.
      - id: select_param_2
        -orig-id: r4
        type: u1
        doc: >
          [CONFIRMED_LIVE] r4 Select-Type parameter 2 (Number of IC etc.): Segment 07,
          Continuously 0f, Randomly 01 (min ICs), Customize 00.
      - id: r5
        -orig-id: r5
        type: u1
        doc: >
          [INFERRED] r5. The doc maps bit 0x10 to the Based-on-Segment distribution,
          but captures show 0x10 set under Based-on-IC too (00 for the Christmas
          preset, 10 for single-layer edits, 12 alongside a segment distribution), so
          the exact meaning is not isolated. Read as raw.
      - id: r6
        -orig-id: r6
        type: u1
        doc: '[INHERITED] r6: unmapped, constant 0x01 in all captures; meaning unconfirmed.'
      - id: brightness_scope_start
        -orig-id: r7
        type: u1
        doc: '[CONFIRMED_LIVE] r7, high end of the Brightness Scope pair r7:r8 (ff00 default -> c639 for a displayed 22-77%).'
      - id: brightness_scope_end
        -orig-id: r8
        type: u1
        doc: '[CONFIRMED_LIVE] r8, low end of the Brightness Scope pair r7:r8.'
      - id: r9
        -orig-id: r9
        type: u1
        doc: '[INHERITED] r9: unmapped, constant 0x00 in all captures; meaning unconfirmed.'
      - id: brightness_speed
        -orig-id: r10
        type: u1
        doc: '[CONFIRMED_LIVE] r10 Brightness Changing Speed (7f/80 ~= 50%, ff = 100%).'
      - id: brightest_retention
        -orig-id: r11
        type: u1
        doc: '[CONFIRMED_LIVE] r11, Brightest retention of the pair r11:r12 (1414 default -> c830 for displayed 200/48).'
      - id: darkest_retention
        -orig-id: r12
        type: u1
        doc: '[CONFIRMED_LIVE] r12, Darkest retention of the pair r11:r12.'
      - id: direction_distribution
        -orig-id: r13
        type: u1
        doc: >
          [CONFIRMED_LIVE] r13 packed byte: bit 0x80 = Direction Backward, OR-ed with
          the distribution value (00 Unified, 01 Based-on-IC, 02 Based-on-Segment) and
          bit 0x01 = colour-gradient (only meaningful under Based-on-Segment, moving 82
          to 83). Values 01/80/81/82/83 seen on the wire.
      - id: colour_speed
        -orig-id: r14
        type: u1
        doc: '[CONFIRMED_LIVE] r14, Colour Changing Speed of the pair r14:r15 (8014 default; 7f/82/b2 seen).'
      - id: colour_retention
        -orig-id: r15
        type: u1
        doc: '[CONFIRMED_LIVE] r15, Colour Retention of the pair r14:r15 (14 default; 6d seen).'
      - id: colour_count
        -orig-id: r16
        type: u1
        doc: '[CONFIRMED_LIVE] r16 = M, number of RGB triplets in the palette; record_len == 23 + 3*M holds byte-exact for M = 1/2/3.'
      - id: palette
        -orig-id: r17
        type: govee_common::rgb
        repeat: expr
        repeat-expr: colour_count
        doc: '[CONFIRMED_LIVE] r17..: M ordered RGB triplets (e.g. ff0000 red, 0000ff blue, 00ff00 green).'
      - id: selected_area_movement
        type: movement
        doc: >
          [CONFIRMED_LIVE] selected-area movement <packed> <interval> <speed>. The
          packed byte carries the enable bit 0x10, the Enter/Exit bit 0x04 and a
          2-bit direction (14..17 seen); 00 disables while interval/speed persist.
      - id: overall_movement
        type: movement
        doc: >
          [CONFIRMED_LIVE] overall movement <packed> <interval> <speed>. Same enable
          bit and 2-bit direction as selected-area but no Enter/Exit bit (10..13 seen);
          00 disables while interval/speed persist.
      - id: priority
        type: u1
        doc: '[CONFIRMED_LIVE] last record byte: Effect Layer Priority, 00 off / 01..05 levels (00/01/02/03 seen).'
    instances:
      applied_area_width_tenths:
        value: '(applied_area & 0xf0) >> 4'
        doc: '[CONFIRMED_LIVE] Applied Area width in tenths (high nibble of r1).'
      applied_area_start_tenths:
        value: 'applied_area & 0x0f'
        doc: '[CONFIRMED_LIVE] Applied Area start in tenths (low nibble of r1).'
      direction_is_backward:
        value: '(direction_distribution & 0x80) != 0'
        doc: '[CONFIRMED_LIVE] r13 bit 0x80: Direction Backward when set.'
  movement:
    doc: |
      A 3-byte movement sub-block <packed> <interval> <speed>. The packed byte's
      enable/direction bits are isolated live (movement-dir/overall-dir/toggle
      captures); interval and speed persist at their last-set values when disabled,
      so their standalone meaning is not independently isolated.
    seq:
      - id: packed
        type: u1
        doc: '[CONFIRMED_LIVE] enable bit 0x10, selected-area Enter/Exit bit 0x04, low 2 bits = direction (0 Fwd, 1 Fwd+Back, 2 Back, 3 Back+Fwd).'
      - id: interval
        type: u1
        doc: '[INFERRED] movement interval; persists when the block is disabled, so not independently isolated.'
      - id: speed
        type: u1
        doc: '[INFERRED] movement speed = round(pct * 2.55); persists when disabled, so not independently isolated.'
    instances:
      enabled:
        value: '(packed & 0x10) != 0'
        doc: '[CONFIRMED_LIVE] movement enable bit 0x10.'
      enter_exit_effect:
        value: '(packed & 0x04) != 0'
        doc: '[CONFIRMED_LIVE] selected-area Enter/Exit bit 0x04 (always 0 for overall movement).'
      direction:
        value: 'packed & 0x03'
        doc: '[CONFIRMED_LIVE] low 2 bits: movement direction 0..3.'
