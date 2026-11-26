meta:
  id: h6022_music_body
  title: Govee H6022 music parameter body
  endian: le
  imports:
    - govee_common
    - govee_shared
doc: |
  H6022 A3 subtype 41 carries the mode, a counted RGB palette and the exact
  mode-specific parameter tail before activation by the 33 05 13 selector.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
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
    size: tail_len
    type:
      switch-on: mode
      cases:
        'music_mode::energetic': style_tail
        'music_mode::rhythm': style_tail
        'music_mode::spectrum': gradient_tail
        'music_mode::rolling': directional_tail
        'music_mode::separation': gradient_tail
        'music_mode::hopping': hopping_tail
        'music_mode::fountain': directional_tail
        'music_mode::meteor': meteor_tail
enums:
  music_mode:
    0x39: energetic
    0x38: rhythm
    0x54: spectrum
    0x63: rolling
    0x55: separation
    0x33: hopping
    0x64: fountain
    0x65: meteor
instances:
  tail_len:
    value: >-
      mode == music_mode::rolling or mode == music_mode::fountain ? 3 :
      mode == music_mode::meteor ? 1 : 2
types:
  style_tail:
    seq:
      - id: style
        type: u1
        valid:
          any-of: [0, 1]
      - id: reserved
        type: u1
        valid: 0
  gradient_tail:
    seq:
      - id: gradient
        type: u1
        valid:
          any-of: [0, 1]
      - id: reserved
        type: u1
        valid: 0
  directional_tail:
    seq:
      - id: gradient
        type: u1
        valid:
          any-of: [0, 1]
      - id: direction
        type: u1
        valid:
          any-of: [0, 1]
      - id: reserved
        type: u1
        valid: 0
  hopping_tail:
    seq:
      - id: gradient
        type: u1
        valid:
          any-of: [0, 1]
      - id: companion
        type: u1
  meteor_tail:
    seq:
      - id: direction
        type: u1
        valid:
          any-of: [0, 1]
