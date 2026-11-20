meta:
  id: h6053_wire_write
  title: Govee H6053 revision-dependent command writes
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: reconstructed H6053 command layouts, without recorded device
  traffic or owner qualification. Pact 1/1 master brightness uses register
  values 20..254; Pact 2/1 uses percentages. Static colour on firmware before
  1.00.12 or hardware before 1.00.00 addresses two bars with submode 0x0d.
  Later static controls address twelve positions, six per bar, with submode
  0x15. An older whole-colour route also uses 0x0d on Pact 1/1 after that
  firmware boundary; these shapes are not interchangeable without revision
  qualification. All frames are 20 bytes, ending in XOR of bytes 0..18.
  Colour-temperature control bounds are 2200..6500 K. Unknown suffixes are
  opaque; physical white rendering, acknowledgements and timing remain
  unqualified.
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
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x04: brightness
    0x05: mode
  mode_sel:
    0x0c: legacy_music
    0x0d: legacy_colour
    0x15: static_colour
  bar_flag:
    0x01: left
    0x10: right
  static_operation:
    0x01: colour
    0x02: brightness
    0x03: brightness_vector
  music_mode:
    0x00: energetic
    0x05: rhythm
    0x06: impact
    0x07: spray
    0x49: beat
    0x50: torch
    0x51: rainbow_ring
    0x52: glitter
types:
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: padding
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
            'mode_sel::legacy_music': legacy_music
            'mode_sel::legacy_colour': legacy_colour
            'mode_sel::static_colour': static_colour
  legacy_music:
    doc: |
      Pact 1/1 uses this selector on every evidenced firmware revision.
      Firmware 1.08.00 adds the four palette-backed modes without changing
      the base codebook or submode. Palette upload uses A3/41 on both Pacts.
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
        value: mode == music_mode::energetic or mode == music_mode::rhythm or mode == music_mode::impact or mode == music_mode::spray
      write_tail_size:
        value: '14 - (mode == music_mode::rhythm ? 1 : 0) - (is_base ? 1 + (has_fixed_colour != 0 ? 4 : 0) : 0)'
  legacy_colour:
    doc: |
      Both bars use target mask 0x11; independent targets are 0x01 and 0x10.
      Kelvin zero means direct RGB. Native white has big-endian Kelvin and
      an RGB companion in the same colour field, with no second RGB triple.
    seq:
      - id: bar_mask
        type: u1
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  static_colour:
    seq:
      - id: operation
        type: u1
        enum: static_operation
      - id: rgb
        type: govee_shared::rgb
        if: operation == static_operation::colour
      - id: kelvin
        type: u2be
        if: operation == static_operation::colour
      - id: companion_rgb
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
        repeat-expr: 12
        if: operation == static_operation::brightness_vector
      - id: unknown_tail
        size-eos: true
