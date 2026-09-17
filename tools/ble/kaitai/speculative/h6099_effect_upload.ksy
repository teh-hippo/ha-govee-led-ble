meta:
  id: h6099_effect_upload
  title: Govee H6099 reassembled scene and ordinary DIY body
  endian: le
  imports:
    - ../govee_shared
    - ../diy_type03
    - ../diy_type04
doc: |
  SPECULATIVE H6099 catalogue upload hypothesis for issue #258. Android 7.6.01
  pact_h6099/Support.isMultiScenesV1 selects ScenesOp.parseSceneV1 types 1/2;
  CmdPtReal.getNewScenesCmdPtReal uses MultipleBleBytes.getMultipleWriteBytesV1
  then SubModeScenesV1, with a little-endian scene selector. Exact-SKU catalogue
  parameters fit the shared type-1 and layered structures. Physical upload,
  activation and restoration remain unqualified. H6099DiyConfig registers
  DiyProtocolParseShare0x00 and RgbIcGraffitiShare0x08 for goods 191. Their V0
  non-old controller uploads shared type04 (no FE prefix) and type03 bodies.
  Graffiti indices address physical ICs, not the 14 logical segments.
  DiyNewEditVm defaults ordinary Sub4Diy activation to code 254. This does not
  authorize arbitrary Advanced or Workshop carriers. Exact physical topology
  and visible behaviour still require owner qualification.
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
