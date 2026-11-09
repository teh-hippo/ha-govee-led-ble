meta:
  id: h60b0_command_write
  title: H60B0 candidate ordinary and source command writes
  endian: le
  imports:
    - ../govee_shared
    - h60b0_music_body
doc: |
  SPECULATIVE: Exact-model command layouts, not confirmed by recorded device
  traffic. Nine colour positions are independent of the bottom white source.
  Source operations preserve suffix octets whose meaning is not established.
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
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x30: zone_enable
    0x41: power_on_behaviour
  multi_sub:
    0x04: scene
    0x0a: diy
    0x0d: static
    0x13: music
    0x2c: source_control
  source:
    1: top_enabled
    2: side_enabled
    3: bottom_enabled
    4: all
    5: colour_sources
  operation:
    1: colour
    2: brightness
    3: secondary
  power_on_state:
    0: previous
    1: "on"
    2: "off"
instances:
  is_static:
    value: opcode == command_op::multi and body.as<multi_cmd>.sub == multi_sub::static
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
  power_on_cmd:
    seq:
      - id: selector
        contents: [0x02]
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
            'multi_sub::static': whole_colour
            'multi_sub::source_control': source_cmd
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
        enum: h60b0_music_body::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: false
  whole_colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  source_cmd:
    seq:
      - id: source
        type: u1
        enum: source
      - id: operation
        type: u1
        enum: operation
      - id: detail
        size: 14
        type:
          switch-on: source
          cases:
            'source::top_enabled': top_body(operation)
            'source::side_enabled': masked_body(operation)
            'source::bottom_enabled': bottom_body(operation)
            'source::all': paged_body(operation)
            'source::colour_sources': paged_body(operation)
  top_body:
    params:
      - id: operation
        type: u1
        enum: operation
    seq:
      - id: colour
        type: colour
        if: operation == operation::colour
      - id: value
        type: u1
        if: operation != operation::colour
      - id: unknown_tail
        size-eos: true
  colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
  masked_body:
    params:
      - id: operation
        type: u1
        enum: operation
    seq:
      - id: colour
        type: colour
        if: operation == operation::colour
      - id: value
        type: u1
        if: operation == operation::brightness
      - id: mask
        type: u2
      - id: unknown_tail
        size-eos: true
  bottom_body:
    params:
      - id: operation
        type: u1
        enum: operation
    seq:
      - id: kelvin
        type: u2be
        if: operation != operation::brightness
      - id: value
        type: u1
        if: operation == operation::brightness
      - id: unknown_tail
        size-eos: true
  paged_body:
    params:
      - id: operation
        type: u1
        enum: operation
    seq:
      - id: colour
        type: colour
        if: operation == operation::colour
      - id: mask
        type: u2
        if: operation == operation::colour
      - id: levels
        type: u1
        repeat: expr
        repeat-expr: 9
        if: operation == operation::brightness
      - id: page
        type: u1
        if: operation == operation::secondary
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: 4
        if: operation == operation::secondary
      - id: unknown_tail
        size-eos: true
