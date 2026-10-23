meta:
  id: h60a6_diy_body
  title: Govee H60A6 native DIY body
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H60A6 native DIY body for #402.  Compatibility hypothesis:
  family 797 uses a complete 0x50-prefixed body with a little-endian payload
  length, background palette and length-delimited typed layers.  This is not
  an A3 logical header.  Each recognised layer has a speed byte and a
  colour-count-prefixed RGB palette.  A payload length of 32 also produces a
  0x50 0x20 prefix; use exact family metadata rather than prefix-only routing.
  Unresolved assumptions: no exact-model BLE capture qualifies these layouts,
  parameter meanings, background flag, editor limits or firmware coverage.
  Unmapped parameters, unknown layer kinds and trailing layer data remain opaque.
seq:
  - id: marker
    contents: [0x50]
  - id: payload_length
    type: u2
    doc: Byte length of the complete body following this field.
  - id: payload
    type: payload
    size: payload_length
types:
  payload:
    seq:
      - id: layer_count
        type: u1
      - id: background_count
        type: u1
      - id: backgrounds
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: background_count
      - id: background_flag
        type: u1
      - id: layers
        type: layer
        repeat: expr
        repeat-expr: layer_count
      - id: opaque
        size-eos: true
  layer:
    seq:
      - id: length
        type: u2
        doc: Number of bytes following this field, including the kind byte.
      - id: kind
        type: u1
        enum: layer_kind
      - id: body
        size: length - 1
        type:
          switch-on: kind
          cases:
            'layer_kind::area_flow': area_flow
            'layer_kind::line_flow': line_flow
            'layer_kind::spread_gather': spread_gather
            'layer_kind::rotation': rotation
            'layer_kind::random_breathing': random_breathing
            'layer_kind::meteor': meteor
            'layer_kind::random_gradient': random_gradient
            'layer_kind::fade': single_parameter
            'layer_kind::breathing': single_parameter
            'layer_kind::flashing': single_parameter
            _: opaque_body
  palette:
    seq:
      - id: colour_count
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: colour_count
  area_flow:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameters
        size: 13
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  line_flow:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameter
        type: u1
      - id: unknown_flag
        type: u1
      - id: point_count
        type: u1
      - id: points
        type: u1
        repeat: expr
        repeat-expr: point_count
      - id: unknown_parameters
        size: 5
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  spread_gather:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameters
        size: 7
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  rotation:
    seq:
      - id: speed
        type: u1
      - id: direction
        type: u1
      - id: angle
        type: u2
      - id: unknown_flag
        type: u1
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  random_breathing:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameters
        size: 2
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  meteor:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameters
        size: 5
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  random_gradient:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameters
        size: 2
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  single_parameter:
    seq:
      - id: speed
        type: u1
      - id: unknown_parameter
        type: u1
      - id: palette
        type: palette
      - id: opaque
        size-eos: true
  opaque_body:
    seq:
      - id: data
        size-eos: true
enums:
  layer_kind:
    1: area_flow
    2: line_flow
    3: spread_gather
    4: rotation
    5: random_breathing
    6: meteor
    7: random_gradient
    8: fade
    9: breathing
    10: flashing
