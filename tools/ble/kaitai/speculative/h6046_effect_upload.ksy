meta:
  id: h6046_effect_upload
  title: Govee H6046 reassembled scene and DIY uploads
  endian: le
  imports:
    - ../govee_shared
doc: |
  H6046.
  Evidence class: exact-model behavioural audit and exact-SKU catalogue
  structures, not captures or hardware qualification. Known Pact 1/1 and 2/1
  admit shared type-1 parameters, type-2 layers and H6046 type-4 flat/mixed DIY.
  This reassembled content starts with marker 1, line count and body kind.
  Physical A3 fragments use the shared 20-byte XOR envelope; this root does not
  duplicate transport fragmentation. Upload acceptance precedes the separate
  16-bit scene/DIY selector. Selector status is not content readback.
  Flat DIY has family, variant, speed and byte-length-prefixed RGB palette.
  Mixed family 255 appends a byte length and up to four family/variant pairs.
  Palette size is 1..8, speed 1..100 with default 50. Family and variant are
  wire selectors, not editor identities. Product eligibility, scene carrier
  selection and storage-slot approval remain profile/catalogue policy.
  Unsupported and AI families are not admitted. No whole-SKU alias is used.
  Unresolved assumptions: nondefault variants, suffix meanings, other revisions
  and visible rendering. Uncertain tails remain opaque without zero validation.
seq:
  - id: header
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: body_kind
    valid:
      any-of: [body_kind::builtin_parameters, body_kind::scene, body_kind::diy]
  - id: content
    type:
      switch-on: kind
      cases:
        'body_kind::builtin_parameters': govee_shared::scene_type1_content
        'body_kind::scene': scene_content
        'body_kind::diy': diy_content
enums:
  body_kind:
    0x01: builtin_parameters
    0x02: scene
    0x04: diy
  effect_family:
    0x00: fade
    0x01: jumping
    0x02: twinkle
    0x05: breathing
    0x08: stream
    0x09: flow
    0x0a: chase
    0x0b: snow
    0x0d: aurora
    0xff: mixed
types:
  scene_content:
    seq:
      - id: num_blocks
        type: u1
      - id: blocks
        type: block
        repeat: expr
        repeat-expr: num_blocks
      - id: unknown_tail
        size-eos: true
  block:
    seq:
      - id: len_body
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: len_body
  diy_content:
    seq:
      - id: family
        type: u1
        enum: effect_family
        valid:
          any-of:
            - effect_family::fade
            - effect_family::jumping
            - effect_family::twinkle
            - effect_family::breathing
            - effect_family::stream
            - effect_family::flow
            - effect_family::chase
            - effect_family::snow
            - effect_family::aurora
            - effect_family::mixed
      - id: variant
        type: u1
      - id: speed
        type: u1
        valid:
          min: 1
          max: 100
      - id: palette_len
        type: u1
        valid:
          expr: _ >= 3 and _ <= 24 and _ % 3 == 0
      - id: palette
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: palette_len / 3
      - id: mix_bytes
        type: u1
        valid:
          expr: _ <= 8 and _ % 2 == 0
        if: family == effect_family::mixed
      - id: pairs
        type: effect_pair
        repeat: expr
        repeat-expr: mix_bytes / 2
        if: family == effect_family::mixed
      - id: unknown_tail
        size-eos: true
    instances:
      default_speed:
        value: 50
  effect_pair:
    seq:
      - id: family
        type: u1
        enum: effect_family
        valid:
          any-of:
            - effect_family::fade
            - effect_family::jumping
            - effect_family::twinkle
            - effect_family::breathing
            - effect_family::stream
            - effect_family::flow
            - effect_family::chase
            - effect_family::snow
            - effect_family::aurora
      - id: variant
        type: u1
