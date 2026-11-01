meta:
  id: h6046_command_write
  title: Govee H6046 command writes
  endian: le
  imports:
    - ../govee_shared
doc: |
  H6046.
  Evidence class: exact-model behavioural audit and source-reconstructed bytes,
  not official-app captures or owner qualification. Known Pact 1/1 and 2/1 use
  this modern layout; no H6053 legacy range or firmware gate is assumed.
  Each frame is 20 bytes, with XOR of bytes 0..18 in the final byte; the
  transport validates that checksum. Ten segments comprise five per bar.
  Unresolved assumptions: other Pact/revision combinations, opaque suffixes,
  timing and physical rendering, including differences between RGBIC/RGBWIC
  revisions. Unknown bytes have no zero-only validation.
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
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
        'command_op::bar_enable': bar_enable_body
        'command_op::swap_bars': swap_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0x33: bar_enable
    0x34: swap_bars
  mode_sel:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static_colour
  static_operation:
    0x01: colour
    0x02: brightness
    0x03: brightness_vector
  bar_flag:
    0x01: left
    0x10: right
  music_mode:
    0x03: rhythm
    0x05: energetic
    0x08: impact
    0x09: spray
    0x49: beat
    0x50: torch
    0x51: rainbow_ring
    0x52: glitter
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
      - id: unknown_tail
        size-eos: true
  bar_enable_body:
    doc: |
      Both flags are written together, independently of master power.
      Left is bit 0x01 and right is bit 0x10. Other bits remain uninterpreted.
    seq:
      - id: mask
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      left_enabled:
        value: (mask & 0x01) != 0
      right_enabled:
        value: (mask & 0x10) != 0
  swap_body:
    doc: |
      Empty logical body. The remaining envelope octets are opaque.
      This swaps bar coordinates, not an absolute direction setting.
      Repeating it can undo the first action; an ACK is not position readback.
    seq:
      - id: unknown_tail
        size-eos: true
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::scene': scene_body
            'mode_sel::diy': diy_body
            'mode_sel::music': music_body
            'mode_sel::static_colour': static_colour_body
  scene_body:
    doc: |
      Little-endian selector, including codes above 255. Uploaded parameters
      must be acknowledged before activation. Readback proves selection only.
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  diy_body:
    doc: Slot selector after an acknowledged DIY upload, not a content read.
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
  static_colour_body:
    doc: |
      RGB with Kelvin zero selects direct RGB. Native white carries big-endian
      Kelvin and a companion RGB preview. Colour and brightness masks are
      little-endian: whole 0x03ff, left 0x001f, right 0x03e0.
      Masked brightness and the complete ten-value brightness vector are
      independent operations. Kelvin candidates span 2000..9000 K; zero is
      not an absent field. Product admission belongs to the exact-SKU profile.
    seq:
      - id: operation
        type: u1
        enum: static_operation
      - id: red
        type: u1
        if: operation == static_operation::colour
      - id: green
        type: u1
        if: operation == static_operation::colour
      - id: blue
        type: u1
        if: operation == static_operation::colour
      - id: kelvin
        type: u2be
        if: operation == static_operation::colour
      - id: preview
        type: govee_shared::rgb
        if: operation == static_operation::colour
      - id: segment_mask
        type: u2le
        if: operation == static_operation::colour
      - id: brightness_percent
        type: u1
        valid:
          max: 100
        if: operation == static_operation::brightness
      - id: brightness_segment_mask
        type: u2le
        if: operation == static_operation::brightness
      - id: brightness_values
        type: u1
        valid:
          max: 100
        repeat: expr
        repeat-expr: 10
        if: operation == static_operation::brightness_vector
      - id: unknown_tail
        size-eos: true
  music_body:
    doc: |
      Sensitivity is 0..99. Rhythm alone carries a calm/style byte before the
      fixed-colour flag. For the four base modes a nonzero fixed flag adds
      target mask 0x01/0x10/0x11 and one RGB triple; a zero flag omits them.
      Unequal bar colours require two ordered selector writes.
      Companion-backed modes carry only mode and sensitivity here, after the
      A3/41 upload has succeeded. RX instead carries two RGB triples.
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
        valid:
          max: 99
      - id: is_calm
        type: u1
        if: mode == music_mode::rhythm
      - id: has_fixed_colour
        type: u1
        if: is_base
      - id: bar_mask
        type: u1
        if: is_base and has_fixed_colour != 0
      - id: fixed_colour
        type: govee_shared::rgb
        if: is_base and has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
    instances:
      is_base:
        value: mode == music_mode::rhythm or mode == music_mode::energetic or mode == music_mode::impact or mode == music_mode::spray
