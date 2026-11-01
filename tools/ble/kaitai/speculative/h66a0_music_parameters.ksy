meta:
  id: h66a0_music_parameters
  title: Govee H66A0 onboard music parameter body
  endian: be
  imports:
    - ../govee_shared
doc: |
  H66A0.  H66A0 music control uploads A3
  command 41 (mode followed by this palette and tail) before sending the mode
  selector.  Default companions carry seven RGB colours, and the mode
  configuration admits 1-8 colours (2-8 for Windmill).  Physical IC count (90
  on uncut H66A0, read via AA 40) controls dependent geometry.
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
        'music_mode::separation': separation_tail
        'music_mode::hopping': hopping_tail
        'music_mode::piano_keys': piano_tail
        'music_mode::fountain': fountain_tail
        'music_mode::day_and_night': daynight_tail
        'music_mode::flowing_light': flowing_light_tail
        'music_mode::painting': painting_tail
        'music_mode::windmill': empty_tail
        'music_mode::splash': empty_tail
        'music_mode::spring': empty_tail
        'music_mode::beat': beat_tail
enums:
  music_mode:
    0x30: bloom
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
    0x53: flowing_light
    0x55: painting
    0x78: windmill
    0x84: splash
    0x85: spring
    0xa9: beat
types:
  empty_tail:
    seq: []
  flowing_light_tail:
    seq:
      - id: direction
        type: u1
  painting_tail:
    seq:
      - id: color_mode
        type: u1
  beat_tail:
    seq:
      - id: prefix
        contents: [0x01]
      - id: order
        type: u1
  bloom_tail:
    seq:
      - id: no_rhythm_speed
        type: u1
      - id: rhythm_speed
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
