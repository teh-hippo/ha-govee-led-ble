meta:
  id: h60b0_diy_body
  title: H60B0 Pact 1/1 and 1/2 native DIY upload
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H60B0 older-revision DIY, not hardware-confirmed.
  Canonical shared bodies prefix this upload with marker 50.
  A3 subtype 58 carries this root without that marker; selector 254
  activates the temporary body. Family 13 combines ripple then side.
  Revision 1/3 uses a different, explicitly qualified schema.
seq:
  - id: family
    type: u1
  - id: body
    type:
      switch-on: family
      cases:
        13: advanced
        _: parameters(family, false)
enums:
  upload_subtype:
    0x58: native_diy
  activation_selector:
    254: temporary
types:
  advanced:
    seq:
      - id: ripple
        type: section(true)
      - id: side
        type: section(false)
      - id: unknown_tail
        size-eos: true
  section:
    params:
      - id: ripple
        type: bool
    seq:
      - id: family
        type: u1
      - id: len_body
        type: u1
      - id: body
        type: parameters(family, ripple)
        size: len_body
        if: family != 0
  parameters:
    params:
      - id: family
        type: u1
      - id: ripple
        type: bool
    seq:
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: palette
        type: palette
      - id: secondary_palette
        type: palette
        if: family == 8 and not ripple
      - id: direction
        type: u1
        if: ripple
      - id: flow_speed
        type: u1
        if: ripple
      - id: unknown_tail
        size-eos: true
  palette:
    seq:
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
