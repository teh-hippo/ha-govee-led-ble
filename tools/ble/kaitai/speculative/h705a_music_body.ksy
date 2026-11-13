meta:
  id: h705a_music_body
  title: H705A candidate music companions
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h705a_music_write
doc: |
  SPECULATIVE: H705A A3/41 companions carry a mode, counted RGB palette and
  mode-specific parameters. Shiny appends three brightness/rate companions;
  Hopping appends background RGB and relative brightness; Jumping and Rolling
  append rotation direction; Firefly is palette-only.
  Older authoring emits two additional zero bytes after direction or Hopping
  parameters, while the current authoring route omits them and uses a different
  Hopping default brightness. The suffix is preserved without invented checks.
  Hardware interpretation of these route differences remains unqualified.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: h705a_music_write::music_mode
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
        'h705a_music_write::music_mode::shiny': shiny_tail
        'h705a_music_write::music_mode::jumping': direction_tail
        'h705a_music_write::music_mode::rolling': direction_tail
        'h705a_music_write::music_mode::hopping': hopping_tail
        'h705a_music_write::music_mode::firefly': empty_tail
  - id: padding
    size-eos: true
enums:
  direction:
    0: clockwise
    1: counterclockwise
types:
  empty_tail:
    seq: []
  shiny_tail:
    seq:
      - id: minimum_brightness
        type: u1
      - id: maximum_brightness
        type: u1
      - id: speed
        type: u1
  direction_tail:
    seq:
      - id: direction
        type: u1
        enum: direction
  hopping_tail:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: rel_brightness
        type: u1
