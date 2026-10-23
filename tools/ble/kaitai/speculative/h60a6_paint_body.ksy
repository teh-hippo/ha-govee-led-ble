meta:
  id: h60a6_paint_body
  title: Govee H60A6 native paint body
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H60A6 native paint body for #402.  Compatibility hypothesis:
  family 798 uses a complete 0x50 0x20-prefixed body with background RGB,
  background brightness, show type and length-delimited layers.  Kind 3
  contains length-delimited colour groups followed by action, speed,
  brightness, priority, duration and four opaque bytes.  All lengths and
  counts wider than one byte are little-endian.  This is not an A3 header.
  Unresolved assumptions: no exact-model BLE capture qualifies every action,
  show type, duration unit, priority rule, editor limit or firmware revision.
  Candidate action codes are 1 through 7; their meanings remain unmapped.
  Unknown layer kinds, extension bytes and opaque fields are preserved.
seq:
  - id: marker
    contents: [0x50, 0x20]
  - id: background
    type: govee_shared::rgb
  - id: background_brightness
    type: u1
  - id: show_type
    type: u1
  - id: layer_count
    type: u1
  - id: layers
    type: layer
    repeat: expr
    repeat-expr: layer_count
  - id: opaque
    size-eos: true
types:
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
            'layer_kind::point_groups': point_groups
            _: opaque_body
  point_groups:
    seq:
      - id: data_length
        type: u2
        doc: Byte length of the group count and colour groups.
      - id: data
        type: colour_groups
        size: data_length
      - id: action
        type: u1
        enum: action_code
      - id: speed
        type: u1
      - id: brightness
        type: u1
      - id: priority
        type: u1
      - id: duration
        type: u2
      - id: opaque
        size: 4
      - id: trailing
        size-eos: true
  colour_groups:
    seq:
      - id: group_count
        type: u2
      - id: groups
        type: colour_group
        repeat: expr
        repeat-expr: group_count
      - id: opaque
        size-eos: true
  colour_group:
    seq:
      - id: point_count
        type: u2
      - id: colour
        type: govee_shared::rgb
      - id: indices
        type: u1
        repeat: expr
        repeat-expr: point_count
  opaque_body:
    seq:
      - id: data
        size-eos: true
enums:
  layer_kind:
    3: point_groups
  action_code:
    1: action_1
    2: action_2
    3: action_3
    4: action_4
    5: action_5
    6: action_6
    7: action_7
