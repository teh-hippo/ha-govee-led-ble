meta:
  id: workshop_body
  title: Govee H617A reassembled Workshop layer-container body (A3 TYPE 0x02, decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
seq:
  - id: header
    type: govee_common::a3_header
  - id: a3_type
    contents: [0x02]
  - id: layer_count
    type: u1
  - id: layers
    type: layer_record
    repeat: expr
    repeat-expr: layer_count
  - id: padding
    type: u1
    valid: 0
    repeat: eos
types:
  layer_record:
    seq:
      - id: record_len
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: record_len
