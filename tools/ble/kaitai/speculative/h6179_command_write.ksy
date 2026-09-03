meta:
  id: h6179_command_write
  title: Govee H6179 speculative "33" command-write envelope
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6179 compatibility hypothesis: exact-SKU command writes use a
  20-byte 0x33 envelope with the candidate power, brightness, mode, scene, DIY,
  static-colour, and music layouts below.
  Unresolved assumptions: no exact-model capture verifies the selectors, field
  meanings, brightness scale, optional music colour, opaque tails, or XOR
  checksum byte.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_opcode
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_opcode::power': power_body
        'command_opcode::brightness': brightness_body
        'command_opcode::mode': mode_body
  - id: checksum
    type: u1
types:
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: opaque
        size-eos: true
  brightness_body:
    seq:
      - id: raw
        type: u1
      - id: opaque
        size-eos: true
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_selector
      - id: payload
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_selector::legacy_colour': legacy_colour_body
            'mode_selector::scene': scene_body
            'mode_selector::diy': diy_body
            'mode_selector::static': static_body
            'mode_selector::music': music_body
  static_body:
    seq:
      - id: rgb_direct
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: rgb_preview
        type: govee_shared::rgb
      - id: opaque
        size-eos: true
  legacy_colour_body:
    doc: Unproved whole-device RGB variant retained as structural evidence only.
    seq:
      - id: colour
        type: govee_shared::rgb
      - id: opaque
        size-eos: true
  scene_body:
    seq:
      - id: scene_id
        type: u1
      - id: opaque
        size-eos: true
  music_body:
    seq:
      - id: effect_id
        type: u1
        enum: music_effect
      - id: sensitivity
        type: u1
      - id: colour_mode
        type: u1
      - id: fixed_colour
        type: govee_shared::rgb
        if: colour_mode != 0
      - id: opaque
        size-eos: true
  diy_body:
    seq:
      - id: diy_id
        type: u2le
      - id: opaque
        size-eos: true
enums:
  command_opcode:
    0x01: power
    0x04: brightness
    0x05: mode
  mode_selector:
    0x02: legacy_colour
    0x04: scene
    0x0a: diy
    0x0d: static
    0x0e: music
  music_effect:
    0x00: mode_0
    0x01: mode_1
