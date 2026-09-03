meta:
  id: h6179_diy_body
  title: Govee H6179 speculative protocol-1.1 DIY body
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6179 #227 compatibility hypothesis: exact-SKU protocol-1.1 DIY
  bodies start with 0xfe and use the candidate single-family or 0xff mixed-family
  palette and pair layouts below.
  Unresolved assumptions: no exact-model capture verifies the family selectors,
  variants, speed, palette length, mixed-pair length or meaning, trailing bytes,
  or transport association.
seq:
  - id: marker
    contents: [0xfe]
  - id: family
    type: u1
  - id: body
    type:
      switch-on: family
      cases:
        '0x00': single_body
        '0x01': single_body
        '0x02': single_body
        '0xff': mixed_body
        _: opaque_body
  - id: opaque
    size-eos: true
types:
  opaque_body:
    seq:
      - id: data
        size-eos: true
  palette:
    seq:
      - id: colours
        type: govee_shared::rgb
        repeat: eos
  effect_pair:
    seq:
      - id: family
        type: u1
      - id: variant
        type: u1
  single_body:
    seq:
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: len_palette
        type: u1
      - id: palette
        type: palette
        size: len_palette
  mixed_body:
    seq:
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: len_palette
        type: u1
      - id: palette
        type: palette
        size: len_palette
      - id: mix_bytes
        type: u1
      - id: pairs
        type: effect_pair
        repeat: expr
        repeat-expr: mix_bytes / 2
