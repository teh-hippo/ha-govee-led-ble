meta:
  id: h6099_music_parameters
  title: Govee H6099 onboard music parameter body
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6099 issue #258.  Android 7.6.01 H6099 music control uploads A3
  command 41 (mode followed by this palette and tail) before sending the mode
  selector.  Default companions carry seven RGB colours, and the mode
  configuration admits 1-8 colours.  Shared music parameter builders define the
  mode-specific tail fields below.  Physical IC count, not fourteen logical
  zones, controls dependent geometry.  Day/Night's app UI parameter indices
  disagree with its payload builder (no segment count is applied, index 0 sets
  speed, and index 1 sets fade), so those UI parameters remain unqualified.
  Energetic's companion upload path differs from the legacy selector path and
  remains unresolved.  No official-app capture or owner qualification yet.
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
enums:
  music_mode:
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
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
