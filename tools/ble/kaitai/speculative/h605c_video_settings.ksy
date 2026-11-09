meta:
  id: h605c_video_settings
  endian: le
doc: |
  SPECULATIVE scalar whole-video brightness, distinct from edge brightness.
  Query AA A9 02 and write 33 A9 02 01 value. The reply contains selector,
  length and value. Firmware admission is declared by the product profile.
seq:
  - id: header
    type: u1
    enum: frame_header
  - id: opcode
    contents: [0xa9]
  - id: setting
    contents: [0x02]
  - id: length
    type: u1
    if: header == frame_header::write
    valid: 1
  - id: value
    type: u1
    if: header == frame_header::write
    valid:
      max: 100
  - id: unknown_tail
    size: 'header == frame_header::write ? 14 : 16'
  - id: checksum
    type: u1
enums:
  frame_header:
    0x33: write
    0xaa: query
