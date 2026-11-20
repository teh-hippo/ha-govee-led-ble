meta:
  id: h6199_pact1_wire_write
  title: Govee H6199 Pact 1 legacy brightness, colour and music writes
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H6199 Pact 1/1 uses a scaled 20..254 brightness
  register and static-colour selector 0x0b with RGB, a two-byte Kelvin field and
  a little-endian fifteen-bit segment mask.  Native Kelvin writes carry the
  temperature's companion RGB in the same colour field as RGB writes.
  Music uses selector 0x0c with a style byte only for Rhythm and no colour
  fields for Energetic.  Hardware delivery and rendering remain unconfirmed.
  The final byte is the XOR of bytes 0 through 18.
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
    0x0b: static_colour
    0x0c: music
  music_mode:
    0x00: energetic
    0x02: rolling
    0x03: spectrum
    0x05: rhythm
types:
  brightness_body:
    seq:
      - id: register
        type: u1
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
            'mode_sel::static_colour': static_colour_body
            'mode_sel::music': music_body
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: segment_mask
        type: u2
      - id: unknown_tail
        size-eos: true
  music_body:
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
        valid:
          max: 1
        if: mode == music_mode::rhythm
      - id: has_fixed_colour
        type: u1
        valid:
          max: 1
        if: mode != music_mode::energetic
      - id: fixed_colour
        type: govee_shared::rgb
        if: mode != music_mode::energetic
      - id: unknown_tail
        size-eos: true
    instances:
      write_tail_size:
        value: 'mode == music_mode::energetic ? 14 : (mode == music_mode::rhythm ? 9 : 10)'
