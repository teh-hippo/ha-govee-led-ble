meta:
  id: h1ab2_diy_body
  title: Govee H1AB2 Accumulation DIY body
  endian: le
  imports:
    - ../govee_shared
    - ../govee_common
doc: |
  SPECULATIVE: H1AB2 Accumulation uploads this native body using A3 command
  58, then activates temporary DIY selector 254. The body carries effect,
  speed, direction, return flag and a counted RGB palette. Its two effect
  styles differ by the return flag; each accepts both directions.
  Background colour is not serialised by this control.
  Firmware-specific extensions and hardware rendering remain unconfirmed.
seq:
  - id: effect
    type: u1
    enum: effect
  - id: speed
    type: u1
  - id: direction
    type: u1
    enum: direction
  - id: return_enabled
    type: u1
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
enums:
  effect:
    0x22: accumulation
  direction:
    1: clockwise
    2: counter_clockwise
  variation:
    0: clockwise
    1: counter_clockwise
    2: clockwise_return
    3: counter_clockwise_return
  upload_subtype:
    0x58: native_diy
  activation_selector:
    254: temporary
  catalogue_family:
    948: accumulation
types:
  upload:
    seq:
      - id: header
        type: govee_common::a3_header
      - id: kind
        contents: [0x58]
      - id: body
        type: h1ab2_diy_body
      - id: padding
        type: u1
        repeat: eos
