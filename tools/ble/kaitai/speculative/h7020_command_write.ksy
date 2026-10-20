meta:
  id: h7020_command_write
  title: H7020 candidate command envelope
  endian: le
  imports:
    - ../command_write
    - ../govee_common
    - ../govee_shared
doc: |
  SPECULATIVE H7020, support PR #363. Candidate commands use the shared
  20-byte envelope, with four-byte masks for up to two fifteen-bulb strings.
  Colour temperature uses white direct RGB and a table-derived companion.
  The configured string count is not physical attachment detection.
  Unresolved assumptions: exact-model captures have not qualified mask width,
  colour appearance, count changes, music parameters, upload activation or ACK
  timing. Unknown suffixes are retained without inferred padding constraints.
  A3/02 layered and A3/04 basic/mixed bodies reuse the shared effect schemas;
  both DIY families activate with a separate DIY slot, not the body effect ID.
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
        'command_op::configured_strings': configured_strings_cmd
        'command_op::power_off_memory': boolean_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x0f: configured_strings
    0x41: power_off_memory
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
      body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 2)
types:
  configured_strings_cmd:
    seq:
      - id: count
        type: u1
        valid:
          any-of: [1, 2]
      - id: unknown_tail
        size-eos: true
  boolean_cmd:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
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
            'multi_sub::music': music_selector
            'multi_sub::static': static_cmd
  music_selector:
    seq:
      - id: mode_id
        type: u1
      - id: sensitivity
        type: u1
      - id: rhythm_response
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  segment_mask:
    seq:
      - id: bits
        type: u4le
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            1: static_color
            2: static_brightness
  static_color:
    seq:
      - id: rgb_direct
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: rgb_preview
        type: govee_shared::rgb
      - id: mask
        type: segment_mask
      - id: unknown_tail
        size-eos: true
  static_brightness:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
      - id: mask
        type: segment_mask
      - id: unknown_tail
        size-eos: true
