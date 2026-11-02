meta:
  id: h6072_command_write
  title: H6072 candidate command envelope
  endian: le
  imports:
    - ../command_write
    - ../govee_common
    - ../govee_shared
doc: |
  H6072.
  Compatibility hypothesis: basic controls, scenes, DIY selection and newer
  static bodies share the common envelope. Legacy static selector 14 places
  its eight-zone mask after an unknown byte; newer selector 15 uses the
  shared static operations. Product revision admission is independent.
  Exact-model evidence, unused bytes, rendering and ACK timing are unqualified.
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
        'command_op::multi_effect': command_write::multi_effect_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0xa3: multi_effect
  multi_sub:
    0x04: scene
    0x0a: diy
    0x14: legacy_static
    0x15: static
instances:
  is_static:
    value: >-
      opcode == command_op::multi and
      (body.as<multi_cmd>.sub == multi_sub::static or
      body.as<multi_cmd>.sub == multi_sub::legacy_static)
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
            'multi_sub::diy': govee_common::diy_selector
            'multi_sub::static': command_write::static_cmd
            'multi_sub::legacy_static': legacy_colour
  legacy_colour:
    seq:
      - id: rgb_direct
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: rgb_preview
        type: govee_shared::rgb
      - id: unknown
        type: u1
      - id: mask
        type: u1
      - id: unknown_tail
        size-eos: true
