meta:
  id: h6117_wire_write
  title: Govee H6117 speculative revision-dependent wire writes
  endian: le
  imports:
    - ../command_write
    - ../govee_common
    - ../govee_shared
    - h6125_wire_write
doc: |
  H6117 compatibility hypothesis; no identified device captures are available.
  Earlier controllers use whole-device 0x02 RGB or masked 0x0b RGB, while
  qualified newer controllers use the shared 0x15 static-colour body.
  Legacy 0x11 music uses a separate codebook from shared 0x13 music.
  Telink master brightness is a 6..254 register; other qualified families
  use 1..100. Register scaling and music eligibility are independent.
  Imported structures describe compatible fields, not sibling capabilities.
  Revision admission, masks and scaling belong to the effective profile.
  Unresolved assumptions: device acceptance, echoes, unused bytes and physical
  rendering. Unknown bodies and tails stay opaque. The last byte is XOR.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': flag_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
        'command_op::gradual': flag_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0xa3: gradual
  mode_sub:
    0x02: whole_device_colour
    0x04: scene
    0x0a: diy
    0x0b: legacy_colour
    0x11: legacy_music
    0x13: music
    0x15: static
  legacy_music_mode:
    0x10: energetic
    0x11: rhythm
    0x12: rolling
    0x13: spectrum
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
types:
  flag_body:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: padding
        size-eos: true
  mode_body:
    seq:
      - id: sub
        type: u1
        enum: mode_sub
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'mode_sub::whole_device_colour': whole_device_colour
            'mode_sub::scene': scene_activate
            'mode_sub::diy': diy_selector
            'mode_sub::legacy_colour': h6125_wire_write::legacy_colour
            'mode_sub::legacy_music': legacy_music_selector
            'mode_sub::music': music_selector
            'mode_sub::static': static_cmd
  whole_device_colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  scene_activate:
    seq:
      - id: code
        type: u2le
      - id: scene_type
        type: u1
      - id: unknown_tail
        size-eos: true
  diy_selector:
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
  music_selector:
    seq:
      - id: selector
        type: govee_common::music_selector
      - id: unknown_tail
        size-eos: true
  legacy_music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: legacy_music_mode
      - id: sensitivity
        type: u1
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'legacy_music_mode::rhythm': h6125_wire_write::rhythm_settings
            'legacy_music_mode::spectrum': h6125_wire_write::colour_settings
            'legacy_music_mode::rolling': h6125_wire_write::colour_settings
            _: h6125_wire_write::opaque_settings
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            1: static_colour
            2: static_brightness
            3: command_write::static_brightness_all
  static_colour:
    seq:
      - id: rgb_direct
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: rgb_preview
        type: govee_shared::rgb
      - id: mask
        type: command_write::segment_mask
      - id: unknown_tail
        size-eos: true
  static_brightness:
    seq:
      - id: percent
        type: u1
      - id: mask
        type: command_write::segment_mask
      - id: unknown_tail
        size-eos: true
