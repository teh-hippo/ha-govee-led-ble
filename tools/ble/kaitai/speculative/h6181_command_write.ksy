meta:
  id: h6181_command_write
  title: Govee H6181 whole-device RGB command envelope
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6181 candidate contract. Ordinary colour uses mode 0D with
  direct RGB, Kelvin BE16 and companion RGB. A separate colour-effect route
  uses mode 02 with RGB, a temperature flag and companion RGB; no hardware
  or firmware boundary between those routes is established.
  Brightness carries the revision's raw register. Legacy scene selectors
  are one byte; later selectors may use the following byte.
  Physical acceptance, acknowledgements and opaque suffixes need owner
  qualification. All frames are 20 bytes with an XOR checksum.
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
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
  - id: checksum
    type: u1
instances:
  is_static:
    value: 'opcode == command_op::mode and body.as<mode_body>.sub_mode == mode_sel::static_colour'
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
  mode_sel:
    0x02: colour_effect
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x13: music
  music_mode:
    0: dynamic
    1: soft
    48: bloom
    49: radiant
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        valid:
          any-of: [0, 1]
      - id: padding
        size-eos: true
  brightness_body:
    seq:
      - id: percent
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
            'mode_sel::scene': scene_body
            'mode_sel::diy': diy_body
            'mode_sel::static_colour': static_colour_body
            'mode_sel::colour_effect': colour_effect_body
            'mode_sel::music': music_body
  music_body:
    doc: |
      Candidate later-revision selector. Readback routes disagree about the
      selector/style positions; a write or ACK does not establish a fresh
      music selector observation.
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: reserved
        type: u1
        if: mode == music_mode::dynamic or mode == music_mode::soft
      - id: has_fixed_colour
        type: u1
        if: mode == music_mode::dynamic or mode == music_mode::soft
      - id: fixed_colour
        type: govee_shared::rgb
        if: (mode == music_mode::dynamic or mode == music_mode::soft) and has_fixed_colour != 0
      - id: padding
        size-eos: true
    instances:
      is_legacy:
        value: mode == music_mode::dynamic or mode == music_mode::soft
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: padding
        size-eos: true
  diy_body:
    seq:
      - id: code
        type: u2le
      - id: padding
        size-eos: true
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: companion_rgb
        type: govee_shared::rgb
      - id: padding
        size-eos: true
  colour_effect_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: temperature_flag
        type: u1
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
