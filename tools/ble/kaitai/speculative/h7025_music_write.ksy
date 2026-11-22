meta:
  id: h7025_music_write
  title: Govee H7025 music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  H7025.
  H7025 music authoring selects the following exact-product IDs.
  Rhythm uses 33 05 13 03, sensitivity, calm flag, and a fixed-colour flag;
  a nonzero fixed-colour flag adds one RGB triple, not a palette.
  Other modes use only ID and sensitivity after a complete A3/41 upload.
  The sensitivity-only editor reuses the resident body without uploading it.
  AA05 status replies parse the same selector fields.
  The reported 33 05 00 shortcut is not emitted.
  Firmware 1.03.13 visibly accepted six-colour Hopping over an authenticated
  BLE V1 session, returning A3 41 48 before the selector acknowledgement.
  Unresolved: other revisions, the leading brightness/power packet, unused
  bytes, and visible application of the remaining modes.
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
    0x8e: sway
    0x59: flow
    0x98: star
    0x8f: twinkle
    0x48: hopping
    0x5a: rolling
    0x37: day_and_night
    0x34: piano_keys
    0x5d: separation
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
        value: mode_id == music_mode::rhythm
      write_tail_size:
        value: '14 - (is_legacy ? 2 + (has_fixed_colour != 0 ? 3 : 0) : 0)'
