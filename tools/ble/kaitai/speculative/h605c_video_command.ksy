meta:
  id: h605c_video_command
  endian: le
doc: |
  SPECULATIVE ordinary H605C video mode. Both registered protocol revisions
  use this long layout. A short alternative belongs to camera calibration,
  which is outside runtime scope. The four percentages are saved edge settings,
  not defaults. Writers canonicalise two reserved bytes to zero; readers retain
  uncertain trailing bytes. Ordinary softness ranges from 0 through 99.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    contents: [0x05]
  - id: mode
    contents: [0x00]
  - id: detail
    type: video_body
    size: 16
  - id: checksum
    type: u1
enums:
  video_source:
    0: movie
    1: game
  video_region:
    0: part
    1: all
types:
  video_body:
    seq:
      - id: region
        type: u1
        enum: video_region
      - id: source
        type: u1
        enum: video_source
      - id: saturation
        type: u1
        valid:
          min: 1
          max: 100
      - id: sound_effects
        type: u1
        valid:
          any-of: [0, 1]
      - id: softness
        type: u1
        valid:
          max: 99
      - id: reserved
        type: u1
      - id: left_percent
        type: u1
        valid:
          max: 100
      - id: top_percent
        type: u1
        valid:
          max: 100
      - id: right_percent
        type: u1
        valid:
          max: 100
      - id: bottom_percent
        type: u1
        valid:
          max: 100
      - id: reserved_end
        type: u1
      - id: unknown_tail
        size-eos: true
