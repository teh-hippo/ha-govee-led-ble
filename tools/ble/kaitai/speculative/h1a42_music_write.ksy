meta:
  id: h1a42_music_write
  title: Govee H1A42 music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  H1A42.  Hardware measurements and
  H1A43 music control select the sixteen mode IDs below over 33 05 13.
  Classic modes (03..06) carry sensitivity, calm flag, fixed-colour flag, and
  optional RGB triple.  Palette modes carry only mode ID and sensitivity after
  an A3 41 companion upload.  AA 05 13 status replies parse the same fields.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    contents: [0x05]
  - id: sub
    contents: [0x13]
  - id: selector
    size: 16
    type: music_selector
  - id: checksum
    type: u1
enums:
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
    0x07: piano_keys
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x35: fountain
    0x37: day_and_night
    0x51: meteor
    0x84: splash
    0x85: spring
    0x92: ripple
    0xa3: orbit
types:
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
        if: is_legacy
      - id: has_fixed_colour
        type: u1
        if: is_legacy
      - id: rgb
        type: govee_shared::rgb
        if: is_legacy and has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
    instances:
      write_tail_size:
        value: '14 - (is_legacy ? 2 + (has_fixed_colour != 0 ? 3 : 0) : 0)'
      is_legacy:
        value: >-
          mode_id == music_mode::rhythm or mode_id == music_mode::spectrum or
          mode_id == music_mode::energetic or mode_id == music_mode::rolling
