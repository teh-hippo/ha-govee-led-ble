meta:
  id: h705a_command_write
  title: H705A candidate command envelope
  endian: le
  imports:
    - ../command_write
    - ../govee_common
    - ../govee_shared
doc: |
  SPECULATIVE: H705A Pact 1/1 and 1/2 ordinary control envelope.
  Logical colour sections contain four physical ICs. RGB, native Kelvin and
  relative brightness select sections with a least-significant-bit-first mask.
  The supported nine-string installation has at most twenty-seven sections.
  Kelvin carries black direct RGB and a table-derived companion colour.
  Scene and DIY selection remain separate from complete acknowledged uploads.
  Physical rendering, revision-specific reply availability and all unused
  suffix bytes remain unconfirmed. Unknown suffixes are not validated as zero.
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
        'command_op::multi_effect': multi_effect_cmd
        'command_op::configured_strings': configured_strings_cmd
        'command_op::refresh_ic': zero_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x0f: configured_strings
    0x42: refresh_ic
    0xa3: multi_effect
  multi_sub:
    0x04: scene
    0x0a: diy
    0x15: static
instances:
  kelvin_direct_rgb:
    value: '[0, 0, 0]'
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
          min: 1
          max: 9
      - id: unknown_tail
        size-eos: true
  zero_body:
    seq:
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  multi_effect_cmd:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: padding
        type: u1
        valid: 0
        repeat: eos
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
            'multi_sub::static': static_cmd
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
    instances:
      tail_size:
        value: 3
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
    instances:
      tail_size:
        value: 10
