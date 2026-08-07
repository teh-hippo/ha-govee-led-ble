meta:
  id: music_body
  title: Govee H617A music-mode wire structures (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: govee_common::music_mode
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
  - id: tail
    size: tail_len
    type:
      switch-on: mode
      cases:
        'govee_common::music_mode::bloom': bloom_tail
        'govee_common::music_mode::shiny': shiny_tail
        'govee_common::music_mode::separation': separation_tail
        'govee_common::music_mode::hopping': hopping_tail
        'govee_common::music_mode::piano_keys': piano_keys_tail
        'govee_common::music_mode::fountain': fountain_tail
        'govee_common::music_mode::day_and_night': day_and_night_tail
  - id: padding
    type: u1
    valid: 0
    repeat: eos
instances:
  tail_len:
    value: >-
      mode == govee_common::music_mode::hopping ? 9 :
      mode == govee_common::music_mode::piano_keys ? 5 :
      mode == govee_common::music_mode::fountain ? 4 :
      mode == govee_common::music_mode::separation ? 3 :
      mode == govee_common::music_mode::shiny ? 3 :
      mode == govee_common::music_mode::day_and_night ? 3 : 2
types:
  bloom_tail:
    seq:
      - contents: [0x0a]
      - id: style_companion
        type: u1
  shiny_tail:
    seq:
      - id: style_companion
        type: u2be
        enum: shiny_style
      - contents: [0x0a]
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
      - contents: [0x62, 0x01, 0x03, 0x02, 0x06]
  piano_keys_tail:
    seq:
      - id: gradient
        type: u1
      - id: key_count
        type: u1
      - contents: [0x0a, 0x04]
      - id: derived_half
        type: u1
  fountain_tail:
    seq:
      - id: start_point
        type: u1
      - id: piece_len
        type: u1
        valid: 0x01
      - id: piece_num
        type: u1
      - id: speed
        type: u1
  day_and_night_tail:
    seq:
      - id: segment_count
        type: u1
      - id: speed
        type: u1
      - id: gradient
        type: u1
  mode_set_frame:
    seq:
      - id: header
        contents: [0x33]
      - id: domain
        contents: [0x05]
      - id: sub
        contents: [0x13]
      - id: mode
        type: u1
        enum: govee_common::music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
      - id: num_colors
        type: u1
        valid:
          max: 4
      - id: colors
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colors
      - id: padding
        type: u1
        valid: 0
        repeat: expr
        repeat-expr: 12 - num_colors * 3
      - id: checksum
        type: u1
enums:
  shiny_style:
    0x0564: dynamic
    0x1446: calm
