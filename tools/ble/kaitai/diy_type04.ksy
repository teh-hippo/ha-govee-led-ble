meta:
  id: diy_type04
  title: Govee H617A reassembled DIY TYPE 0x04 body — Flat DIY + Combo DIY (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
seq:
  - id: header
    type: govee_common::a3_header
  - id: a3_type
    contents: [0x04]
  - id: family
    type: u1
  - id: body
    type:
      switch-on: family
      cases:
        0xff: combo_body
        _: flat_body
types:
  palette:
    seq:
      - id: colours
        type: govee_shared::rgb
        repeat: eos
  family_variant:
    seq:
      - id: family
        type: u1
      - id: variant
        type: u1
  flat_body:
    seq:
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: len_palette
        type: u1
        valid:
          expr: _ % 3 == 0
      - id: palette
        type: palette
        size: len_palette
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  combo_body:
    seq:
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: len_palette
        type: u1
        valid:
          expr: _ % 3 == 0
      - id: palette
        type: palette
        size: len_palette
      - id: seqlen
        type: u1
        valid:
          expr: _ % 2 == 0
      - id: pairs
        type: family_variant
        repeat: expr
        repeat-expr: seqlen / 2
      - id: padding
        type: u1
        valid: 0
        repeat: eos
