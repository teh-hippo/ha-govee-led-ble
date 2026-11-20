meta:
  id: h1ab2_music_parameters
  title: Govee H1AB2 onboard music palette and parameters
  endian: be
  imports:
    - ../govee_shared
    - h6099_music_parameters
doc: |
  SPECULATIVE: H1AB2 uploads mode, counted RGB palette and mode parameters
  through A3 command 41 before selecting onboard music. Classic selectors
  have no companion. Piano Keys uses mode 07. The parameter structures below
  share the counted-palette shapes independently of product mode numbering.
  Physical IC count qualifies dependent defaults and ranges.
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
        'music_mode::bloom': h6099_music_parameters::bloom_tail
        'music_mode::shiny': h6099_music_parameters::shiny_tail
        'music_mode::separation': h6099_music_parameters::separation_tail
        'music_mode::hopping': h6099_music_parameters::hopping_tail
        'music_mode::piano_keys': h6099_music_parameters::piano_tail
        'music_mode::fountain': h6099_music_parameters::fountain_tail
        'music_mode::day_and_night': h6099_music_parameters::daynight_tail
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
  empty_tail:
    seq: []
