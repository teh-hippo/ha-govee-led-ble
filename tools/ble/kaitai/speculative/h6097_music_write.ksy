meta:
  id: h6097_music_write
  title: Govee H6097 music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6097 support for issue #431.  Classic selectors 03, 04 and 06
  carry sensitivity, style and optional fixed RGB.  Energetic (05) instead
  uploads a companion before its mode/sensitivity-only selector, as do the
  newer modes.  Unknown suffixes, rendered results, ACK timing and revision
  differences need exact-device qualification.
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
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
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
        value: mode_id == music_mode::rhythm or mode_id == music_mode::spectrum or mode_id == music_mode::rolling
