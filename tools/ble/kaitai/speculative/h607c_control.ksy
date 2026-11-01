meta:
  id: h607c_control
  title: H607C candidate pole, base and power-on settings
  endian: le
  imports:
    - h60a_bulk
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: pole/base writes are independent selector/boolean
  commands. Power-on writes carry selector 02 and previous/on/off state;
  its query uses selector zero and replies retain an independent open flag.
  Device-info AA replies and EE/30 asynchronous flags have different envelopes.
  Gradual colour change uses the independent ordinary A3 boolean register;
  its AA/A3 query reply is not a multipart upload result.
  Unknown flags and suffixes remain opaque. Persistence and timing are unqualified.
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
        'command::power_on_behaviour': power_on_command
        'command::gradual': gradual_state
  - id: checksum
    type: u1
enums:
  command:
    0x30: zone_enable
    0x41: power_on_behaviour
    0xa3: gradual
  zone:
    0: pole_enabled
    1: base_enabled
  native_flag:
    1: master
    2: pole
    4: base
types:
  gradual_state:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
  gradual_query:
    seq:
      - id: header
        contents: [0xaa, 0xa3]
      - id: unknown_tail
        size: 17
      - id: checksum
        type: u1
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
  power_on_command:
    seq:
      - id: selector
        contents: [0x02]
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
  device_info_query:
    seq:
      - id: header
        contents: [0xaa, 0x07, 0x08]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
  power_on_query:
    seq:
      - id: header
        contents: [0xaa, 0x41, 0x00]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
  device_info:
    seq:
      - id: brightness
        type: u1
      - id: flags
        type: native_flags
      - id: unknown_tail
        size-eos: true
  native_flags:
    seq:
      - id: mask
        type: u1
    instances:
      master_enabled:
        value: '(mask & native_flag::master.to_i) != 0'
      pole_enabled:
        value: '(mask & native_flag::pole.to_i) != 0'
      base_enabled:
        value: '(mask & native_flag::base.to_i) != 0'
      unknown_mask:
        value: 'mask & 0xf8'
  zone_notification:
    seq:
      - id: header
        contents: [0xee, 0x30]
      - id: body
        size: 17
        type: zone_notification_body
      - id: checksum
        type: u1
    instances:
      domain:
        value: '"zone_enable"'
      is_on:
        value: body.flags.master_enabled
      pole_enabled:
        value: body.flags.pole_enabled
      base_enabled:
        value: body.flags.base_enabled
  zone_notification_body:
    seq:
      - id: unknown_prefix
        type: u1
      - id: flags
        type: native_flags
      - id: unknown_tail
        size-eos: true
  power_on_state:
    seq:
      - id: open_flag
        type: u1
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
