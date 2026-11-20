meta:
  id: h1ab2_paint_body
  title: Govee H1AB2 physical-IC painted effect
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - ../diy_type03
doc: |
  SPECULATIVE: H1AB2 paint uses the A3 type-03 counted colour-group layout.
  Positions address physical ICs, not the ten ordinary colour segments.
  Each motion has its own H1AB2 selector; these are not interchangeable with
  the similarly named selectors of other products. Transport fill is kept
  separate from authored content and firmware-specific extensions are unknown.
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
    type: diy_type03::paint_group
    repeat: expr
    repeat-expr: num_groups
  - id: padding
    type: u1
    repeat: eos
enums:
  effect:
    0x39: clockwise
    0x3a: counter_clockwise
    0x3b: cycle
    0x3c: gradient
    0x3d: twinkle
    0x3e: breathe
