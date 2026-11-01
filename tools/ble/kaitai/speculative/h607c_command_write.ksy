meta:
  id: h607c_command_write
  title: H607C candidate ordinary control envelope
  endian: le
  imports:
    - ../command_write
    - h607c_music_write
doc: |
  H607C.
  Compatibility hypothesis: common power, percentage brightness, scene and
  DIY selectors use the ordinary 33 envelope. Static selector 15 carries
  two-byte masks and thirteen brightness values. Independent native zone
  and power-on settings use h607c_control.
  Unused bytes, rendering, replies and revision timing need qualification.
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
        'command_op::power': command_write::power_cmd
        'command_op::brightness': command_write::brightness_cmd
        'command_op::multi': multi_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
  multi_sub:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
instances:
  is_static:
    value: >-
      opcode == command_op::multi and body.as<multi_cmd>.sub == multi_sub::static and
      (body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 1 or
      body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 2 or
      body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 3)
types:
  multi_cmd:
    seq:
      - id: sub
        type: u1
        enum: multi_sub
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'multi_sub::scene': command_write::scene_activate
            'multi_sub::diy': diy_selector
            'multi_sub::music': h607c_music_write::music_selector
            'multi_sub::static': static_cmd
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            1: command_write::static_color
            2: command_write::static_brightness
            3: static_brightness_all
  static_brightness_all:
    seq:
      - id: segment_percent
        type: u1
        valid:
          max: 100
        repeat: expr
        repeat-expr: 13
      - id: unknown_tail
        size-eos: true
  diy_selector:
    seq:
      - id: code
        type: u2le
      - id: companion
        type: u2le
      - id: unknown_tail
        size-eos: true
