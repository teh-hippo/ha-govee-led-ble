meta:
  id: h6127_wire_write
  title: Govee H6127 legacy whole-strip wire commands
  endian: le
  imports:
    - ../govee_shared
    - h6125_wire_write
doc: |
  SPECULATIVE H6127 candidate. Before firmware 1.03.01, colour uses
  submode 02 with RGB, a temperature flag and companion RGB. Onboard music
  uses submode 01; Spectrum and Rolling carry RGB directly, without a
  fixed-colour flag. A separate retained music route uses submode 03.
  Early inline DIY carries a one-byte selector, family, variation, speed
  and four RGB slots. Later DreamColor writes use independently selected
  compatible codecs. Brightness register bounds belong to the profile.
  Physical acceptance, revision boundaries and unused bytes need owner
  confirmation. Unknown bytes are not validated as zero padding.
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
        'command_op::brightness': h6125_wire_write::brightness_body
        'command_op::mode': mode_body
        'command_op::gradual': flag_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x04: brightness
    0x05: mode
    0x14: gradual
  mode_sub:
    0x01: legacy_music
    0x02: whole_device_colour
    0x03: colour_music
    0x07: inline_diy
  legacy_music_mode:
    0: energetic
    1: spectrum
    2: rolling
    3: rhythm
types:
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
            'mode_sub::legacy_music': legacy_music_selector
            'mode_sub::whole_device_colour': whole_device_colour
            'mode_sub::colour_music': colour_music
            'mode_sub::inline_diy': inline_diy
  whole_device_colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: temperature_flag
        type: u1
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  legacy_music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: legacy_music_mode
      - id: sensitivity
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: mode_id == legacy_music_mode::spectrum or mode_id == legacy_music_mode::rolling
      - id: unknown_tail
        size-eos: true
    instances:
      observed_selector:
        value: mode_id
      has_fixed_colour:
        value: mode_id == legacy_music_mode::spectrum or mode_id == legacy_music_mode::rolling
  colour_music:
    seq:
      - id: automatic
        type: u1
      - id: sensitivity
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: automatic != 0
      - id: unknown_tail
        size-eos: true
  inline_diy:
    seq:
      - id: code
        type: u1
      - id: family
        type: u1
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: 4
  flag_body:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
  query:
    seq:
      - id: header
        contents: [0xaa]
      - id: domain
        type: u1
        enum: query_domain
      - id: unknown_tail
        size: 17
      - id: checksum
        type: u1
    enums:
      query_domain:
        0x14: gradual
