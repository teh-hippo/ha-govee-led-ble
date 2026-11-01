meta:
  id: h607c_diy_body
  title: H607C candidate native single and paired DIY body
  endian: le
  imports:
    - ../govee_shared
doc: |
  H607C.
  Compatibility hypothesis: native bodies begin with 0b and a family byte.
  Composite 153 stores two effect/length/parameter sections, without
  repeating each section's native marker or family. A zero effect and
  zero length disable that effect section, independently of lamp power.
  Transport command 56 and activation selector 254 are separate namespaces.
  Variant-specific eligibility, rendering and persistent slot behaviour
  require qualification; opaque suffixes are preserved.
seq:
  - id: marker
    contents: [0x0b]
  - id: family
    type: u1
    enum: family
  - id: body
    size-eos: true
    type:
      switch-on: family
      cases:
        'family::paired': paired_parameters
        'family::gradual': parameters(family)
        'family::breathe': parameters(family)
        'family::stream': parameters(family)
        'family::colour_wall': parameters(family)
        'family::shimmer': parameters(family)
        'family::chase': parameters(family)
        'family::shock': parameters(family)
        'family::drip': parameters(family)
        'family::lava': parameters(family)
  - id: unknown_tail
    size-eos: true
enums:
  family:
    106: gradual
    107: breathe
    108: stream
    109: colour_wall
    110: shimmer
    111: chase
    112: shock
    113: drip
    114: lava
    153: paired
  upload_subtype:
    0x56: native_diy
  activation_selector:
    254: temporary
  variant:
    0: primary
    13: native_13
    14: native_14
    88: native_88
    89: native_89
types:
  paired_parameters:
    seq:
      - id: pole
        type: zone
      - id: base
        type: zone
      - id: unknown_tail
        size-eos: true
  zone:
    seq:
      - id: family
        type: u1
        enum: family
      - id: len_body
        type: u1
      - id: body
        size: len_body
        type:
          switch-on: family
          cases:
            'family::gradual': parameters(family)
            'family::breathe': parameters(family)
            'family::stream': parameters(family)
            'family::colour_wall': parameters(family)
            'family::shimmer': parameters(family)
            'family::chase': parameters(family)
            'family::shock': parameters(family)
            'family::drip': parameters(family)
            'family::lava': parameters(family)
        if: len_body != 0
  parameters:
    params:
      - id: family
        type: u1
        enum: family
    seq:
      - id: variant
        type: u1
        enum: variant
      - id: speed
        type: u1
      - id: first_palette
        type: palette
      - id: second_palette
        type: palette
        if: family == family::shimmer or family == family::drip
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
