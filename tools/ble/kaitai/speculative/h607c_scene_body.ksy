meta:
  id: h607c_scene_body
  title: H607C candidate layered scene parameter
  endian: le
  imports:
    - ../govee_shared
doc: |
  H607C.
  Catalogue type 6 carries a marker-prefixed, length-delimited layer container.
  H607C hardware accepted the type-6 catalogue body over LAN as A3 subtype 0a,
  with the leading 0a moved into the upload subtype. A generic 02 prefix
  produced a visibly different scene. This is a visual transport observation
  against the Platform API, not BLE capture evidence.
  Common layer fields retain their existing encoding; their excess contains the
  V2 trailer described below.
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
