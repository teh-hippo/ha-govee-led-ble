meta:
  id: h66a0_music_write
  title: Govee H66A0 music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  H66A0.  H66A0 music authoring selects
  the sixteen mode IDs below over 33 05 13.  Classic modes (03..06) carry
  sensitivity, calm flag, fixed-colour flag, and optional RGB triple.  Newer
  modes (30..A9) carry only mode ID and sensitivity after an A3 41 companion
  upload.  AA 05 13 status replies parse the same selector fields.
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
    0x30: bloom
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
    0x53: flowing_light
    0x55: painting
    0x78: windmill
    0x84: splash
    0x85: spring
    0xa9: beat
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
