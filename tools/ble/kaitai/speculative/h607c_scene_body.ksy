meta:
  id: h607c_scene_body
  title: H607C candidate layered scene parameter
  endian: le
  imports:
    - ../govee_shared
doc: |
  H607C.
  Compatibility hypothesis: catalogue type 6 carries a marker-prefixed
  length-delimited layer container. A3 upload uses subtype 0a and removes
  that marker once. Common layer fields retain their existing encoding;
  their excess contains the V2 trailer described below.
  Catalogue bodies establish structure, not BLE acceptance or rendering.
  Sub-device mapping, extension semantics and the tail remain unqualified.
seq:
  - id: marker
    contents: [0x0a]
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
  catalogue_type:
    6: layered_scene
  upload_subtype:
    0x0a: layered_scene
types:
  record:
    seq:
      - id: len_body
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: len_body
  layer_trailer:
    seq:
      - id: sub_device
        type: u1
      - id: len_extension
        type: u1
      - id: extension
        size: len_extension
      - id: tail
        type: u1
      - id: unknown
        size-eos: true
