meta:
  id: h6053_effect_upload
  title: Govee H6053 reassembled effect uploads
  endian: le
  imports:
    - ../govee_shared
    - h6046_effect_upload
    - h6181_diy_body
doc: |
  SPECULATIVE: reconstructed H6053 effect envelopes, not captured traffic.
  RGB, RGBIC and flat/mixed DIY use the compatible type 1, 2 and 4 bodies.
  Pact 1/1 flat DIY instead uses A1/02, with a leading FE byte on the current
  authoring route; that prefix does not establish a disposable storage slot.
  Pact 2/1 flat DIY uses A3/type 4. Both Pacts use A3 for scenes and music.
  Workshop RGB, RGBIC V1 and RGBIC V2 select scenes 198, 402 and 403
  respectively, independently of community shared-scene selectors 199/401.
  RGBIC V2 removes its source prefix before A3/type 0A transmission.
  Opaque content is retained without claiming editable semantics.
  Upload acknowledgement precedes selection; neither confirms rendering or
  stored content. Unknown physical IC count must not become twelve ICs.
seq:
  - id: header
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: body_kind
    valid:
      any-of: [body_kind::builtin_parameters, body_kind::scene, body_kind::diy, body_kind::scene_v2]
  - id: content
    type:
      switch-on: kind
      cases:
        'body_kind::builtin_parameters': rgb_upload
        'body_kind::scene': scene_content
        'body_kind::diy': h6046_effect_upload::diy_content
        'body_kind::scene_v2': scene_content
enums:
  body_kind:
    0x01: builtin_parameters
    0x02: scene
    0x04: diy
    0x0a: scene_v2
types:
  frame:
    seq:
      - id: envelope
        type: h6181_diy_body::frame
  a1_diy_body:
    seq:
      - id: prefix
        contents: [0xfe]
      - id: body
        type: h6046_effect_upload::diy_content
  rgb_upload:
    seq:
      - id: body
        type: rgb_content
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  rgb_content:
    seq:
      - id: config
        type: u1
        valid:
          expr: layout <= 1 and colour_stride >= 3 and colour_stride <= 5
      - id: num_steps
        type: u1
      - id: steps
        type: rgb_step
        repeat: expr
        repeat-expr: num_steps
      - id: num_palette
        type: u1
        if: layout == 0
      - id: palette
        type: rgb_colour(colour_stride)
        repeat: expr
        repeat-expr: num_palette
        if: layout == 0
    instances:
      layout:
        value: (config >> 4) & 7
      colour_stride:
        value: config & 7
      brightness_flag:
        value: (config & 0x80) != 0
  rgb_step:
    seq:
      - id: param
        type: govee_shared::scene_type1_step
      - id: colour
        type: rgb_colour(_parent.colour_stride)
        if: _parent.layout == 1
  rgb_colour:
    params:
      - id: stride
        type: u1
    seq:
      - id: colour
        type: govee_shared::rgb
      - id: extra
        size: stride - 3
  scene_content:
    seq:
      - id: num_blocks
        type: u1
      - id: blocks
        type: h6046_effect_upload::block
        repeat: expr
        repeat-expr: num_blocks
      - id: unknown_tail
        size-eos: true
  scene_v2_source:
    seq:
      - id: marker
        contents: [0x0a]
      - id: content
        type: scene_content
  v2_extension:
    doc: V2 decodes the common layer's excess through this structure; V1 retains it without reinterpretation.
    seq:
      - id: kind
        type: u1
      - id: len_content
        type: u1
      - id: content
        size: len_content
      - id: suffix
        type: u1
      - id: unknown_tail
        size-eos: true
