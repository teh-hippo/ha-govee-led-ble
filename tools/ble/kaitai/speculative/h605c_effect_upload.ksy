meta:
  id: h605c_effect_upload
  title: H605C reassembled scenes, painted and palette DIY uploads
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE exact-model A3 content contract. The shared fragmenter supplies
  the marker, line count and subtype. Completion precedes a separate 16-bit
  little-endian scene or DIY selector; the selector is not content readback.
  Types 1 and 2 carry palette scenes and RGBIC layers. Type 3 paints physical
  IC indices, not the fourteen logical static selections; obtain installed
  IC count independently. Type 4 carries palette DIY and mixed pairs.
  Palette families and variations are exact-model product data. Music-family
  DIY uses sensitivity; other flat and mixed effects use speed 1..100.
  Painted effects use the independent 0..100 speed range.
  RGBIC Workshop uploads use the layered body and scene selector 402.
  This selector belongs to the product contract, not the chosen upload codec.
  Workshop authoring normalises each layer's brightness algorithm to version 1,
  retaining the lower flag nibble. Native catalogue parameters are not rewritten.
  The common effect adapter serialises these structures. Opaque suffixes
  include transport fill; nonzero values are not invented validation errors.
seq:
  - id: marker
    contents: [1]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: kind
  - id: body
    type:
      switch-on: kind
      cases:
        'kind::palette_scene': govee_shared::scene_type1_content
        'kind::layered_scene': layered_scene
        'kind::painted': painted
        'kind::palette_diy': palette_diy
enums:
  kind:
    1: palette_scene
    2: layered_scene
    3: painted
    4: palette_diy
  family:
    0: fade
    1: jumping
    2: blinking
    3: marquee
    4: music
    8: stream
    9: flow
    10: chase
    255: mixed
  painted_effect:
    2: cycle
    9: clockwise
    10: counter_clockwise
    15: twinkle
    19: gradient
    20: breathe
types:
  layered_scene:
    seq:
      - id: num_layers
        type: u1
      - id: layers
        type: layer
        repeat: expr
        repeat-expr: num_layers
      - id: unknown_tail
        size-eos: true
  layer:
    seq:
      - id: len_body
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: len_body
  palette_diy:
    seq:
      - id: family
        type: u1
        enum: family
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: len_palette
        type: u1
      - id: palette
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: len_palette / 3
      - id: len_pairs
        type: u1
        if: family == family::mixed
      - id: pairs
        type: pair
        repeat: expr
        repeat-expr: len_pairs / 2
        if: family == family::mixed
      - id: unknown_tail
        size-eos: true
  pair:
    seq:
      - id: family
        type: u1
        enum: family
      - id: variant
        type: u1
  painted:
    seq:
      - id: effect
        type: u1
        enum: painted_effect
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
      - id: unknown_tail
        size-eos: true
  paint_group:
    seq:
      - id: num_indices
        type: u1
      - id: colour
        type: govee_shared::rgb
      - id: indices
        type: u1
        repeat: expr
        repeat-expr: num_indices
