meta:
  id: h6159_wire_write
  title: Govee H6159 whole-strip RGB writes
  endian: be
  imports:
    - h6181_command_write
    - ../govee_shared
doc: |
  SPECULATIVE H6159 candidate wire contract, awaiting recorded device traffic.
  Telink colour uses mode 02 with RGB, a temperature flag and companion RGB;
  later controllers use mode 0D with Kelvin BE16. Brightness is a 6..254
  register on Telink and percentage on the later Pact route.
  Before firmware 1.03.00, onboard music uses mode 03 without an effect
  selector. Later Telink firmware uses mode 0E; the Pact route uses mode 13.
  Palette selectors 48/49 follow an acknowledged A3/41 upload.
  Scenes and DIY carry little-endian 16-bit selectors. Unknown tails remain
  opaque; successful delivery does not establish hardware rendering.
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
        'command_op::power': h6181_command_write::power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
  mode_sel:
    0x02: legacy_colour
    0x03: legacy_music
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x0e: music
    0x13: modern_music
  music_mode:
    0: dynamic
    1: soft
    48: bloom
    49: radiant
types:
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: padding
        size-eos: true
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::legacy_colour': h6181_command_write::colour_effect_body
            'mode_sel::legacy_music': legacy_music_body
            'mode_sel::scene': h6181_command_write::scene_body
            'mode_sel::diy': h6181_command_write::diy_body
            'mode_sel::static_colour': h6181_command_write::static_colour_body
            'mode_sel::music': music_body
            'mode_sel::modern_music': h6181_command_write::music_body
  legacy_music_body:
    seq:
      - id: has_fixed_colour
        type: u1
      - id: sensitivity
        type: u1
      - id: fixed_colour
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: padding
        size-eos: true
    instances:
      mode:
        value: music_mode::dynamic
      write_tail_size:
        value: '14 - (has_fixed_colour != 0 ? 3 : 0)'
  music_body:
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: has_fixed_colour
        type: u1
        if: is_legacy
      - id: fixed_colour
        type: govee_shared::rgb
        if: is_legacy and has_fixed_colour != 0
      - id: padding
        size-eos: true
    instances:
      is_legacy:
        value: mode == music_mode::dynamic or mode == music_mode::soft
      write_tail_size:
        value: '14 - (is_legacy ? 1 + (has_fixed_colour != 0 ? 3 : 0) : 0)'
