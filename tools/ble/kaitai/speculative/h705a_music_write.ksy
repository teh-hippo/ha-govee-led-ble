meta:
  id: h705a_music_write
  title: H705A candidate onboard music selector
  endian: le
doc: |
  SPECULATIVE: H705A selects onboard music with mode and sensitivity.
  Energetic is selector-only; the other five modes configure an acknowledged
  A3/41 companion first. Sensitivity-only changes retain the resident companion.
  Legacy colour/style fields are not editable selector parameters.
  Physical operation, revision differences and unknown suffixes await capture.
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
    5: energetic
    49: shiny
    74: jumping
    72: hopping
    81: firefly
    113: rolling
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
      is_legacy:
        value: false
      write_tail_size:
        value: 14
