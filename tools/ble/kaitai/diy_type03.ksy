meta:
  id: diy_type03
  title: Govee H617A reassembled DIY "TYPE 0x03" body - Finger Sketch + Vibrant (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
seq:
  - id: header
    type: govee_common::a3_header
  - id: body_type
    contents: [0x03]
  - id: effect
    type: u1
    enum: effect
  - id: speed
    type: u1
  - id: brightness
    type: u1
  - id: background
    type: govee_shared::rgb
  - id: num_groups
    type: u1
  - id: groups
    type: paint_group
    repeat: expr
    repeat-expr: num_groups
  - id: padding
    type: u1
    valid: 0
    repeat: eos
enums:
  effect:

    # () and protocol.py _SKETCH_MOTION_CODES (custom_effects.py).
    0x02: cycle
    0x09: clockwise
    0x0a: counter_clockwise
    0x0f: twinkle
    0x13: gradient
    0x14: breathe
types:
  paint_group:
    seq:
      - id: num_segment_indices
        type: u1
      - id: fill
        type: govee_shared::rgb
      - id: segment_indices
        type: u1
        repeat: expr
        repeat-expr: num_segment_indices
