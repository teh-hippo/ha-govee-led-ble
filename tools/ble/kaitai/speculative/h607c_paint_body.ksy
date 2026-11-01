meta:
  id: h607c_paint_body
  title: H607C candidate native graffiti and static paint body
  endian: le
  imports:
    - ../govee_shared
doc: |
  H607C.
  Compatibility hypothesis: native paint uses direction, rate, background
  brightness/RGB and count-prefixed colour/position groups.
  Static paint selects native direction 9 under A3 transport command 03,
  then separately activates selector 900. Neither 9 nor 900 is an extra
  transport header. Pole/base physical budgets are product data, not a
  uniform logical-segment scale. Rendering and restoration are unqualified.
seq:
  - id: direction
    type: u1
    enum: direction
  - id: speed
    type: u1
    valid:
      max: 100
  - id: background_brightness
    type: u1
  - id: background
    type: govee_shared::rgb
  - id: num_groups
    type: u1
  - id: groups
    type: group
    repeat: expr
    repeat-expr: num_groups
  - id: unknown_tail
    size-eos: true
enums:
  direction:
    2: native_2
    9: upward
    10: downward
    15: native_15
    19: native_19
    20: native_20
  upload_subtype:
    3: paint
  activation_selector:
    900: static_paint
types:
  group:
    seq:
      - id: num_positions
        type: u1
      - id: colour
        type: govee_shared::rgb
      - id: positions
        type: u1
        repeat: expr
        repeat-expr: num_positions
