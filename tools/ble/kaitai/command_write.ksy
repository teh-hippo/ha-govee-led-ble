meta:
  id: command_write
  title: Govee H617A "33" command-write envelope (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
doc: |
  H617A 20-byte command frame. The final byte is the XOR of bytes 0 through 18.
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
        'command_op::power': power_cmd
        'command_op::brightness': brightness_cmd
        'command_op::multi': multi_cmd
        'command_op::multi_effect': multi_effect_cmd
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
    0x13: music
    0x15: static
types:
  multi_effect_cmd:
    seq:
      - id: flag
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  power_cmd:
    seq:
      - id: is_on
        type: u1
  brightness_cmd:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
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
            'multi_sub::scene': scene_activate
            'multi_sub::diy': govee_common::diy_selector
            'multi_sub::music': govee_common::music_selector
            'multi_sub::static': static_cmd
  scene_activate:
    seq:
      - id: code
        type: u2le
      - id: scene_type
        type: u1
  segment_mask:
    seq:
      - id: bits
        type: u2le
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            0x01: static_color
            0x02: static_brightness
            0x03: static_brightness_all
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
  static_brightness:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
      - id: mask
        type: segment_mask
  static_brightness_all:
    seq:
      - id: segment_percent
        type: u1
        valid:
          max: 100
        repeat: eos
