meta:
  id: scene_body
  title: Govee H617A reassembled scene / rgbicv2 record-container body (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
seq:
  - id: header
    type: govee_common::a3_header
  - id: scene_type
    type: u1
    enum: scene_type
    valid:
      eq: scene_type::scene_v2
  - id: num_records
    type: u1
  - id: records
    type: record
    repeat: expr
    repeat-expr: num_records
  - id: padding
    type: u1
    valid: 0
    repeat: eos
enums:
  scene_type:
    0: scene_v0
    1: scene_v1
    2: scene_v2
types:
  record:
    seq:
      - id: len_body
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: len_body
