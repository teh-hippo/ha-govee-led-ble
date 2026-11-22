meta:
  id: h8604_settings
  title: Govee H8604 native settings
  endian: le
  imports:
    - h60a_bulk
doc: |
  SPECULATIVE exact H8604 power-on-memory and gradual settings for all three
  registered protocol revisions. Power-on state shares the common previous/on/
  off codebook and is selected through register 0x41. Gradual uses 0xa3.
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
        'command::power_on_behaviour': power_on_command
        'command::gradual': gradual_state
        'command::zone_enable': zone_enable
        'command::box_light': box_light
  - id: checksum
    type: u1
enums:
  command:
    0x41: power_on_behaviour
    0x36: zone_enable
    0xa3: gradual
    0xb6: box_light
  zone:
    0: left_bar_enabled
    1: right_bar_enabled
    2: middle_enabled
types:
  power_on_command:
    seq:
      - id: selector
        contents: [0x02]
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
  gradual_state:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
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
  box_light:
    seq:
      - id: enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: brightness
        type: u1
        valid:
          min: 1
          max: 100
      - id: automatic
        type: u1
        valid:
          any-of: [0, 1]
      - id: effect
        type: u1
        valid:
          max: 10
      - id: unknown_tail
        size-eos: true
  power_on_query:
    seq:
      - id: header
        contents: [0xaa, 0x41, 0x02]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
  gradual_query:
    seq:
      - id: header
        contents: [0xaa, 0xa3]
      - id: unknown_tail
        size: 17
      - id: checksum
        type: u1
  device_info_query:
    seq:
      - id: header
        contents: [0xaa, 0x07, 0x08]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
