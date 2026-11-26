meta:
  id: h1a42_music_parameters
  title: Govee H1A42 music parameter body
  endian: be
  imports:
    - ../govee_shared
doc: |
  H1A42.  H1A43 music control uploads this payload under A3
  subtype 0x41 before the 33 05 13 music selector for palette-backed modes.
  Physical IC count controls Piano, Fountain and Day/Night geometry.
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
        'music_mode::bloom': bloom_tail
        'music_mode::shiny': shiny_tail
        'music_mode::separation': separation_tail
        'music_mode::hopping': hopping_tail
        'music_mode::piano_keys': piano_tail
        'music_mode::fountain': fountain_tail
        'music_mode::day_and_night': daynight_tail
        'music_mode::meteor': empty_tail
        'music_mode::splash': empty_tail
        'music_mode::spring': empty_tail
        'music_mode::ripple': empty_tail
        'music_mode::orbit': empty_tail
enums:
  music_mode:
    0x07: piano_keys
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x35: fountain
    0x37: day_and_night
    0x51: meteor
    0x84: splash
    0x85: spring
    0x92: ripple
    0xa3: orbit
types:
  bloom_tail:
    seq:
      - id: no_rhythm_speed
        type: u1
      - id: rhythm_speed
        type: u1
  shiny_tail:
    seq:
      - id: minimum_brightness
        type: u1
      - id: maximum_brightness
        type: u1
      - id: speed
        type: u1
  separation_tail:
    seq:
      - id: point
        type: u1
      - id: gradient
        type: u1
      - id: companion
        type: u1
  hopping_tail:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: rel_brightness
        type: u1
      - id: speed
        type: u1
      - id: piece_length_min
        type: u1
      - id: piece_length_max
        type: u1
      - id: piece_count_min
        type: u1
      - id: piece_count_max
        type: u1
  piano_tail:
    seq:
      - id: gradient
        type: u1
      - id: key_count
        type: u1
      - id: speed
        type: u1
      - id: off_minimum
        type: u1
      - id: off_maximum
        type: u1
  fountain_tail:
    seq:
      - id: start_point
        type: u1
      - id: piece_length
        type: u1
      - id: piece_count
        type: u1
      - id: speed
        type: u1
  daynight_tail:
    seq:
      - id: piece_count
        type: u1
      - id: speed
        type: u1
      - id: gradient
        type: u1
  empty_tail:
    seq: []
