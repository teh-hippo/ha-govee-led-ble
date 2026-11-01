meta:
  id: h607c_music_write
  title: H607C candidate onboard music selector
  endian: le
doc: |
  H607C.
  Compatibility hypothesis: selector 13 carries the native mode and
  sensitivity after its companion upload. Paired mode 130 selects independent
  pole/base sections. Mode 115 retains a numeric name until its presentation
  semantics are established independently.
  Unknown suffixes, reply coverage and rendering remain unqualified.
seq:
  - id: header
    contents: [0x33, 0x05, 0x13]
  - id: selector
    size: 16
    type: music_selector
  - id: checksum
    type: u1
enums:
  music_mode:
    51: hopping
    79: fusion
    81: shiny
    114: rhythm
    115: native_115
    116: magic
    130: paired
    131: colour_dots
    132: splash
    133: spring
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
