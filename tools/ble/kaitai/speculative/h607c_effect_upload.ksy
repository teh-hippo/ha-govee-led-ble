meta:
  id: h607c_effect_upload
  title: H607C candidate reassembled multipart uploads
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h607c_scene_body
    - h607c_music_body
    - h607c_music_write
    - h607c_diy_body
    - h607c_paint_body
    - h607c_dreamview_group
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: catalogue/body family and transport command are
  independent. The scene command itself supplies its catalogue marker once.
  Music adds its mode after command 41; native DIY uses command 56 and
  native paint command 03. Music DreamView has separate palette, protocol,
  membership and member-scene commands.
  Member-scene assignments require independently sourced operation/effect/
  activation metadata, not an ordinary lamp scene-type number.
  Unknown suffixes are retained; actual acceptance and rendering are unqualified.
seq:
  - id: header
    type: govee_common::a3_header
  - id: kind
    type: u1
    enum: kind
  - id: content
    type:
      switch-on: kind
      cases:
        'kind::paint': h607c_paint_body
        'kind::layered_scene': layered_scene
        'kind::music': music
        'kind::dreamview_palette': palette
        'kind::dreamview_protocols': protocols
        'kind::native_diy': h607c_diy_body
        'kind::dreamview_scene': scene_assignments
        'kind::dreamview_group': h607c_dreamview_group
  - id: padding
    type: u1
    valid: 0
    repeat: eos
enums:
  kind:
    0x03: paint
    0x0a: layered_scene
    0x41: music
    0x51: dreamview_palette
    0x55: dreamview_protocols
    0x56: native_diy
    0x58: dreamview_scene
    0x60: dreamview_group
types:
  layered_scene:
    seq:
      - id: num_records
        type: u1
      - id: records
        type: h607c_scene_body::record
        repeat: expr
        repeat-expr: num_records
  music:
    seq:
      - id: mode
        type: u1
        enum: h607c_music_write::music_mode
      - id: body
        type:
          switch-on: mode
          cases:
            'h607c_music_write::music_mode::paired': h607c_music_body::paired_parameters
            _: h607c_music_body::parameters(mode)
  palette:
    seq:
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
  protocols:
    seq:
      - id: num_members
        type: u1
      - id: members
        type: protocol_pair
        repeat: expr
        repeat-expr: num_members
  protocol_pair:
    seq:
      - id: protocol_type
        type: u1
      - id: protocol_version
        type: u1
  scene_assignments:
    seq:
      - id: num_groups
        type: u1
      - id: groups
        type: scene_group
        repeat: expr
        repeat-expr: num_groups
  scene_group:
    seq:
      - id: num_members
        type: u1
      - id: reversed_macs
        size: 6
        repeat: expr
        repeat-expr: num_members
      - id: operation
        type: u1
      - id: len_effect
        type: u2le
      - id: effect
        size: len_effect
      - id: len_activation
        type: u1
      - id: activation
        size: len_activation
