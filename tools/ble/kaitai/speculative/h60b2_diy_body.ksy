meta:
  id: h60b2_diy_body
  title: H60B2 candidate length-prefixed native DIY
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: Native family 803 uploads as A3 subtype 0x58, then activates
  DIY selector 254. The little-endian length bounds the variant and palette
  section. Variants 4, 6 and 7 prepend direction 13 or 14 before speed.
  Unknown variants and suffixes remain opaque; no recorded traffic confirms
  this candidate authoring contract.
seq:
  - id: len_body
    type: u2
  - id: body
    size: len_body
    type: body
  - id: unknown_tail
    size-eos: true
enums:
  catalogue_family:
    803: native_diy
  upload_subtype:
    0x58: native_diy
  activation:
    254: native_diy
  variant:
    0: fade
    1: breathe
    2: jump
    3: blink
    4: chase
    5: shimmer
    6: bloom
    7: stream
    8: colour_wall
    9: drip
  direction:
    13: up
    14: down
types:
  body:
    seq:
      - id: variant
        type: u1
        enum: variant
      - id: direction
        type: u1
        enum: direction
        if: variant == variant::chase or variant == variant::bloom or variant == variant::stream
      - id: speed
        type: u1
      - id: num_palette
        type: u1
      - id: palette
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_palette
      - id: unknown_tail
        size-eos: true
