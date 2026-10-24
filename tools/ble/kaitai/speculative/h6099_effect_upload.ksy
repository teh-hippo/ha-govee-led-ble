meta:
  id: h6099_effect_upload
  title: Govee H6099 reassembled scene and ordinary DIY body
  endian: le
  imports:
    - ../govee_shared
    - ../diy_type03
    - ../diy_type04
doc: |
  SPECULATIVE H6099 catalogue upload hypothesis for issue #258.  Android 7.6.01
  H6099 scene handling uploads type-1 and type-2 A3 bodies before activating a
  little-endian scene selector.  Exact-SKU catalogue parameters fit the shared
  type-1 and layered structures.  Physical upload, activation, and restoration
  remain unqualified.  Goods type 191 also uploads shared type-04 Basic/Mixed
  bodies (without an FE prefix) and type-03 Graffiti bodies, then activates
  ordinary 0x0a DIY with default code 254.  Graffiti indices address physical
  ICs, not the 14 logical segments.  This does not authorise arbitrary Advanced
  or Workshop carriers.  Exact physical topology and visible behaviour still
  require owner qualification.
  H6097 issue #431 independently shares type-1/type-2 scenes and type-03/type-04
  DIY bodies with default selector 254, its own family bounds and 24 physical
  ICs.  Its selector-only native scenes do not upload a type-0 body.
seq:
  - id: header
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: body_kind
    valid:
      any-of: [body_kind::builtin_parameters, body_kind::scene, body_kind::painted, body_kind::basic]
  - id: content
    type:
      switch-on: kind
      cases:
        'body_kind::builtin_parameters': govee_shared::scene_type1_content
        'body_kind::scene': scene_content
    if: kind == body_kind::builtin_parameters or kind == body_kind::scene
  - id: diy_bytes
    size-eos: true
    if: kind == body_kind::painted or kind == body_kind::basic
instances:
  diy:
    pos: 0
    type:
      switch-on: kind
      cases:
        'body_kind::painted': diy_type03
        'body_kind::basic': diy_type04
    if: kind == body_kind::painted or kind == body_kind::basic
enums:
  body_kind:
    0x01: builtin_parameters
    0x02: scene
    0x03: painted
    0x04: basic
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
