meta:
  id: h1ab2_music_write
  title: Govee H1AB2 onboard music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H1AB2 Pacts 1/1 and 1/2 use a 33 05 13 selector.
  Classic modes carry style and optional fixed RGB; palette modes follow an
  A3 41 upload and carry only mode and sensitivity. Piano Keys is mode 07,
  not the 34 selector used by several other RGBIC products.
  Exact firmware-specific acceptance and trailing status bytes are unconfirmed.
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
      is_legacy:
        value: >-
          mode_id == music_mode::rhythm or mode_id == music_mode::spectrum or
          mode_id == music_mode::energetic or mode_id == music_mode::rolling
      write_tail_size:
        value: '14 - (is_legacy ? 2 + (has_fixed_colour != 0 ? 3 : 0) : 0)'
