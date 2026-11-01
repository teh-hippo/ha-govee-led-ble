meta:
  id: h1a42_music_parameters
  title: Govee H1A42 music parameter body
  endian: le
  imports:
    - ../govee_shared
doc: |
  H1A42.  H1A43 music control
  uploads this payload under A3 subtype 0x41 before the 33 05 13 music selector
  for palette-backed modes.
seq:
  - id: mode
    type: u1
    enum: music_mode
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
  - id: tail
    type:
      switch-on: mode
      cases:
        'music_mode::splash': empty_tail
        'music_mode::spring': empty_tail
        'music_mode::ripple': empty_tail
        'music_mode::orbit': empty_tail
enums:
  music_mode:
    0x84: splash
    0x85: spring
    0x92: ripple
    0xa3: orbit
types:
  empty_tail:
    seq: []
