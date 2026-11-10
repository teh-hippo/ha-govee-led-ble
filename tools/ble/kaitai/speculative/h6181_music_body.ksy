meta:
  id: h6181_music_body
  title: Govee H6181 later-revision onboard music palettes
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h617a_control_payload
doc: |
  SPECULATIVE H6181 BK/FRK firmware >=2.04.00 candidate music palettes.
  A3/41 uploads carry a mode, counted RGB palette and mode-specific tail.
  Bloom uses 10 followed by 80 for dynamic or 20 for soft.
  Radiant uses 5/100 for dynamic or 20/70 for soft, followed by 10.
  The selected palette contains 1..8 colours. The editor seed is one red
  colour, not a claim about a factory palette.
  The selector follows the completed upload. Opaque suffixes are retained.
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
    size: 'mode == music_mode::bloom ? 2 : 3'
    type:
      switch-on: mode
      cases:
        'music_mode::bloom': h617a_control_payload::bloom_tail
        'music_mode::radiant': h617a_control_payload::shiny_tail
  - id: padding
    type: u1
    repeat: eos
enums:
  music_mode:
    48: bloom
    49: radiant
