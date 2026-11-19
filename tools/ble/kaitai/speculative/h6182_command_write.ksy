meta:
  id: h6182_command_write
  title: Govee H6182 whole-strip commands
  endian: be
  imports:
    - h6181_command_write
    - h6159_wire_write
doc: |
  SPECULATIVE H6182 contract, awaiting recorded device traffic.
  Ordinary colour uses mode 0D with RGB, Kelvin BE16 and companion RGB.
  The older controller and colour-effect route use mode 02 with RGB,
  a temperature flag and companion RGB. No revision boundary between
  those colour write routes has been established.
  Telink brightness uses a 20..254 register; other hardware uses percent.
  Legacy onboard music uses mode 03, fixed-colour flag, sensitivity 0..99
  and optional RGB. Later Pact controllers use mode 13 and may qualify
  palette selectors 48/49 through firmware and hardware identity.
  Scene and DIY selectors share the whole-strip little-endian envelope.
  Unknown suffix bytes remain opaque.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: h6181_command_write::command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'h6181_command_write::command_op::power': h6181_command_write::power_body
        'h6181_command_write::command_op::brightness': h6181_command_write::brightness_body
        'h6181_command_write::command_op::mode': mode_body
  - id: checksum
    type: u1
enums:
  mode_sel:
    0x02: colour_effect
    0x03: legacy_music
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x13: music
types:
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
            'mode_sel::colour_effect': h6181_command_write::colour_effect_body
            'mode_sel::legacy_music': h6159_wire_write::legacy_music_body
            'mode_sel::scene': h6181_command_write::scene_body
            'mode_sel::diy': h6181_command_write::diy_body
            'mode_sel::static_colour': h6181_command_write::static_colour_body
            'mode_sel::music': h6181_command_write::music_body
