meta:
  id: h6093_projector
  title: H6093 native projector appearance and layered effects
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: exact-model projector formats without an attributable BLE capture.
  Catalogue bodies carry marker 48 followed by length-delimited layers.
  Native scene uploads omit that marker and use subtype 05; authored DIY uses
  subtype 58 and selector FE. Ordinary projector appearance uses subtype 0C
  followed by mode 0C. Pact 1/1 carries one palette; Pact 1/2 and 2/1 insert a
  palette-control selector and can address the coarse and fine patterns separately.
  Unknown trailing bytes are retained. Physical rendering and later-revision
  independent appearance readback remain unqualified.
  Pattern 04 selects colour flow, independently of physical aurora movement.
seq:
  - id: marker
    contents: [0x48]
  - id: num_layers
    type: u1
  - id: layers
    type: layer_record
    repeat: expr
    repeat-expr: num_layers
  - id: opaque_tail
    size-eos: true
enums:
  command:
    0x05: mode
    0x30: setting
    0x31: local_sound
    0x32: local_volume
  setting:
    1: projection_power
    3: pairing_prompt
    4: quiet_start
    6: local_sound_enabled
    7: dreamview_laser
  upload_kind:
    0x05: scene
    0x0c: appearance
    0x58: diy
  catalogue_family:
    712: projector
  palette_control:
    1: unified
    2: separate
  appearance_control:
    0: unified
    1: separate
  pattern:
    1: fade
    2: breathe
    3: flash
    4: colour_flow
types:
  audio_write:
    seq:
      - id: header
        contents: [0x33]
      - id: opcode
        type: u1
        enum: command
        valid:
          any-of: [command::local_sound, command::local_volume]
      - id: body
        type:
          switch-on: opcode
          cases:
            'command::local_sound': sound_body
            'command::local_volume': volume_body
      - id: checksum
        type: u1
  sound_body:
    seq:
      - id: playing
        type: u1
        valid:
          any-of: [0, 1]
      - id: code
        type: u1
      - id: opaque_tail
        size: 15
  volume_body:
    seq:
      - id: level
        type: u1
      - id: opaque_tail
        size: 16
  setting_write:
    seq:
      - id: header
        contents: [0x33]
      - id: opcode
        type: u1
        enum: command
        valid: command::setting
      - id: body
        type: setting_body
      - id: checksum
        type: u1
  setting_body:
    seq:
      - id: selector
        type: u1
        enum: setting
      - id: enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: opaque_tail
        size: 15
  power_query:
    seq:
      - id: header
        contents: [0xaa, 0x34]
      - id: opaque_tail
        size: 17
      - id: checksum
        type: u1
  activation:
    seq:
      - id: header
        contents: [0x33]
      - id: opcode
        type: u1
        enum: command
        valid: command::mode
      - id: body
        type: activation_body
      - id: checksum
        type: u1
  activation_body:
    seq:
      - id: sub_mode
        type: u1
        enum: upload_kind
        valid: upload_kind::appearance
      - id: opaque_tail
        size: 16
  read_frame:
    seq:
      - id: header
        contents: [0xac]
      - id: index
        type: u1
      - id: body
        size: 17
        type:
          switch-on: index
          cases:
            0: first_frame
      - id: checksum
        type: u1
    types:
      payload:
        seq:
          - id: records
            type: appearance_record
            repeat: expr
            repeat-expr: 1
      appearance_record:
        seq:
          - id: body
            type: appearance(false)
        instances:
          domain:
            value: 12
  first_frame:
    seq:
      - id: frame_count
        type: u2
      - id: final_size
        type: u1
      - id: command
        contents: [0x03]
      - id: discriminator
        contents: [0x05]
      - id: payload
        size: 12
  read_query:
    seq:
      - id: header
        contents: [0xac, 0x03, 0x05, 0x0c]
      - id: opaque_tail
        size: 15
      - id: checksum
        type: u1
  upload:
    seq:
      - id: marker
        contents: [0x01]
      - id: frame_count
        type: u1
      - id: kind
        type: u1
        enum: upload_kind
      - id: body
        size-eos: true
        type:
          switch-on: kind
          cases:
            'upload_kind::scene': effect_body
            'upload_kind::diy': effect_body
  effect_body:
    seq:
      - id: num_layers
        type: u1
      - id: layers
        type: layer_record
        repeat: expr
        repeat-expr: num_layers
      - id: transport_fill
        size-eos: true
  palette:
    seq:
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
  source:
    seq:
      - id: enabled
        type: u1
      - id: brightness
        type: u1
      - id: pattern
        type: u1
        enum: pattern
      - id: speed
        type: u1
      - id: palette
        type: palette
  stars:
    seq:
      - id: enabled
        type: u1
      - id: brightness
        type: u1
      - id: flicker_enabled
        type: u1
      - id: flicker_speed
        type: u1
      - id: movement_enabled
        type: u1
      - id: movement_speed
        type: u1
  aurora:
    seq:
      - id: movement_speed
        type: u1
      - id: direction
        type: u1
      - id: control
        type: u1
        enum: palette_control
      - id: first
        type: source
      - id: second
        type: source
        if: control == palette_control::separate
  layer_record:
    seq:
      - id: len_body
        type: u2
      - id: body
        size: len_body
        type: layer
  layer:
    seq:
      - id: aurora
        type: aurora
      - id: stars
        type: stars
      - id: duration
        type: u2
      - id: opaque_tail
        size-eos: true
  appearance_palette:
    seq:
      - id: enabled
        type: u1
      - id: palette
        type: palette
  appearance:
    params:
      - id: expanded
        type: bool
    seq:
      - id: stars
        type: stars
      - id: aurora_enabled
        type: u1
      - id: movement_speed
        type: u1
      - id: brightness
        type: u1
      - id: pattern
        type: u1
        enum: pattern
      - id: effect_speed
        type: u1
      - id: control
        type: u1
        enum: appearance_control
        if: expanded
      - id: palette
        type: palette
        if: not expanded or control == appearance_control::unified
      - id: coarse
        type: appearance_palette
        if: expanded and control == appearance_control::separate
      - id: fine
        type: appearance_palette
        if: expanded and control == appearance_control::separate
      - id: opaque_tail
        size-eos: true
