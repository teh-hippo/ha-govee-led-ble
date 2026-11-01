meta:
  id: h6072_music_write
  title: H6072 candidate onboard music selector
  endian: le
  imports:
    - h6076_music_write
doc: |
  H6072.
  Compatibility hypothesis: the six legacy selectors and six companion-backed
  selectors share the floor-lamp music records. Product admission and companion
  defaults are independently qualified for H6072.
  Complete owner captures, unknown suffixes and physical rendering are unqualified.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    contents: [0x05]
  - id: sub
    contents: [0x0f]
  - id: selector
    size: 16
    type: h6076_music_write::music_selector
  - id: checksum
    type: u1
