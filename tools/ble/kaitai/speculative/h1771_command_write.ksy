meta:
  id: h1771_command_write
  title: H1771 candidate ordinary command writes
  endian: le
  imports:
    - ../govee_shared
    - h1771_music_body
doc: |
  SPECULATIVE: H1771 commands reconstructed from model behaviour, not confirmed
  by device traffic.  These commands do not establish device or revision
  qualification.  The 0x15 colour and relative-brightness forms use masks;
  another path supplies a page of relative brightness values.  Unknown fields
  and suffixes remain opaque.
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
        'command_op::zone_enable': zone_enable
        'command_op::power_on_behaviour': power_on_cmd
        'command_op::gradual': gradual_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x36: zone_enable
    0x41: power_on_behaviour
    0xa3: gradual
  multi_sub:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
  source:
    0: source_0_enabled
    1: source_1_enabled
  power_on_selector:
    0x02: state
  power_on_state:
    0: previous
    1: "on"
    2: "off"
instances:
  is_static:
    value: >-
      opcode == command_op::multi and body.as<multi_cmd>.sub == multi_sub::static and
      (body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 1 or
      body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 2 or
      body.as<multi_cmd>.sub_body.as<static_cmd>.static_sub == 3)
types:
  power_cmd:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_cmd:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  zone_enable:
    seq:
      - id: source
        type: u1
        enum: source
      - id: enabled
        type: u1
      - id: unknown_tail
        size-eos: true
  gradual_cmd:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
  power_on_cmd:
    seq:
      - id: selector
        type: u1
        enum: power_on_selector
      - id: state
        type: u1
        enum: power_on_state
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
            'multi_sub::scene': selector
            'multi_sub::diy': selector
            'multi_sub::music': music_selector
            'multi_sub::static': static_cmd
  selector:
    seq:
      - id: code
        type: u2
      - id: unknown_tail
        size-eos: true
  music_selector:
    seq:
      - id: mode
        type: u1
        enum: h1771_music_body::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
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
            3: paged_brightness
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
      - id: mask
        type: segment_mask
      - id: unknown_tail
        size-eos: true
  paged_brightness:
    seq:
      - id: page
        type: u1
      - id: segment_percent
        type: u1
        repeat: expr
        repeat-expr: 4
      - id: unknown_tail
        size-eos: true
  segment_mask:
    seq:
      - id: bits
        type: u2
