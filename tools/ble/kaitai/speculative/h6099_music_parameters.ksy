meta:
  id: h6099_music_parameters
  title: Govee H6099 onboard music parameter body
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6099 issue #258. Android 7.6.01 pact_h6099/detail/mode/MusicMode.d
  uses MultipleController4Music (A3 command 41, mode followed by this palette/tail)
  before ControllerMode. MusicEffect supplies seven default RGB colours and
  SubMusicModeConfig qualifies 1-8 colours. Shared RgbMusicZhanFang, RgbMusicCuiCan,
  RgbicMusicYueDong, RgbicMusicGangQinJian, RgbicMusicDuiJi and RgbicMusicZhouYe
  name the fields below; MusicMode itself appends Separation's companion.
  Physical IC count, not fourteen logical zones, controls dependent geometry.
  Day/Night's app UI indices disagree with its controller application: no segment
  setter is called, index 0 sets speed and index 1 sets fade. Those UI parameters
  remain unqualified. Energetic's new-detail upload differs from the legacy path
  and remains unresolved. No official-app capture or owner qualification yet.
seq:
  - id: mode
    type: u1
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
        0x30: bloom_tail
        0x31: shiny_tail
        0x32: separation_tail
        0x33: hopping_tail
        0x34: piano_tail
        0x35: fountain_tail
        0x37: daynight_tail
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
