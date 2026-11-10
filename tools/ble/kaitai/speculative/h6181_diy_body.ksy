meta:
  id: h6181_diy_body
  title: Govee H6181 legacy palette DIY upload
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6181 legacy A1 command-02 body. The first byte is the uploaded
  DIY selector, followed by family, variant, speed, palette byte length,
  RGB triples and mixed-component byte length/pairs. Imported shared bodies
  replace their original leading marker with selector FE.
  Families 0, 1 and 2 are fade, jumping and twinkle. FF combines at most four
  family/variant pairs. Up to eight palette colours and speed 0..100 are
  offered. Frame padding and unknown suffixes are not semantic fields.
seq:
  - id: selector
    type: u1
  - id: family
    type: u1
    enum: effect_family
  - id: variant
    type: u1
  - id: speed
    type: u1
  - id: len_palette
    type: u1
  - id: palette
    type: palette
    size: len_palette
  - id: len_components
    type: u1
  - id: components
    type: effect_pair
    repeat: expr
    repeat-expr: len_components / 2
  - id: unknown_tail
    size-eos: true
enums:
  effect_family:
    0: fade
    1: jumping
    2: twinkle
    255: mixed
types:
  palette:
    seq:
      - id: colours
        type: govee_shared::rgb
        repeat: eos
  effect_pair:
    seq:
      - id: family
        type: u1
        enum: effect_family
      - id: variant
        type: u1
