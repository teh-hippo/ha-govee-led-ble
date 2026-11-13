meta:
  id: h60b2_control
  title: H60B2 candidate head power and retained settings
  endian: le
  imports:
    - h607c_control
doc: |
  SPECULATIVE: Independent head writes use zero-based bottom, middle and top
  selectors. AA36 returns three independent flags; EE30 instead carries packed
  master and head flags in its second payload byte. Power-on and gradual
  registers share their structural codecs with other products, not their policy.
  Unknown suffixes and flag bits remain opaque. Hardware confirmation is pending.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command::zone_enable': zone_enable
        'command::power_on_behaviour': h607c_control::power_on_command
        'command::gradual': h607c_control::gradual_state
  - id: checksum
    type: u1
enums:
  command:
    0x36: zone_enable
    0x41: power_on_behaviour
    0xa3: gradual
  zone:
    0: bottom_enabled
    1: middle_enabled
    2: top_enabled
types:
  zone_enable:
    seq:
      - id: zone
        type: u1
        enum: zone
      - id: enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
  device_info_query:
    seq:
      - id: header
        contents: [0xaa, 0x36]
      - id: unknown_tail
        size: 17
      - id: checksum
        type: u1
  source_state:
    seq:
      - id: bottom
        type: u1
      - id: middle
        type: u1
      - id: top
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      bottom_enabled:
        value: bottom == 1
      middle_enabled:
        value: middle == 1
      top_enabled:
        value: top == 1
  zone_notification:
    seq:
      - id: header
        contents: [0xee, 0x30]
      - id: unknown_prefix
        type: u1
      - id: flags
        type: u1
      - id: unknown_tail
        size: 15
      - id: checksum
        type: u1
    instances:
      is_on:
        value: (flags & 1) != 0
      bottom_enabled:
        value: (flags & 2) != 0
      middle_enabled:
        value: (flags & 4) != 0
      top_enabled:
        value: (flags & 8) != 0
