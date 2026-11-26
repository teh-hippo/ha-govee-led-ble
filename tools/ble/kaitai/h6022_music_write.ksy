meta:
  id: h6022_music_write
  title: Govee H6022 music selector
  endian: le
doc: |
  H6022 selects each onboard music mode with 33 05 13, followed by the mode
  and sensitivity.  Mode parameters travel in a preceding A3 41 upload.
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
    0x39: energetic
    0x38: rhythm
    0x54: spectrum
    0x63: rolling
    0x55: separation
    0x33: hopping
    0x64: fountain
    0x65: meteor
types:
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      write_tail_size:
        value: 14
      is_legacy:
        value: false
