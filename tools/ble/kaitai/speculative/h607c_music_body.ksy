meta:
  id: h607c_music_body
  title: H607C candidate single and paired music companion
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h607c_music_write
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: music uploads have the two-byte command header
  41/mode. Paired mode has separately bounded pole/base sections.
  Palette bodies retain mode-specific parameters; only independently
  established fields are named. Hopping's physical piece counts are not
  logical colour segments. Unknown parameters stay opaque.
  Palette rendering, unused tails and result timing remain unqualified.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: h607c_music_write::music_mode
  - id: body
    type:
      switch-on: mode
      cases:
        'h607c_music_write::music_mode::paired': paired_parameters
        _: parameters(mode)
  - id: padding
    type: u1
    valid: 0
    repeat: eos
instances:
  num_palette:
    value: body.as<parameters>.num_palette
    if: mode != h607c_music_write::music_mode::paired
  palette:
    value: body.as<parameters>.palette
    if: mode != h607c_music_write::music_mode::paired
  tail:
    value: body.as<parameters>.tail
    if: mode != h607c_music_write::music_mode::paired
types:
  paired_parameters:
    seq:
      - id: pole
        type: zone
      - id: base
        type: zone
  zone:
    seq:
      - id: mode
        type: u1
        enum: h607c_music_write::music_mode
      - id: len_parameters
        type: u1
      - id: body
        size: len_parameters
        type: parameters(mode)
  parameters:
    params:
      - id: mode
        type: u1
        enum: h607c_music_write::music_mode
    seq:
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
            'h607c_music_write::music_mode::hopping': hopping_parameters
            _: opaque_parameters
  hopping_parameters:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: background_brightness
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
      - id: unknown_tail
        size-eos: true
  opaque_parameters:
    seq:
      - id: unknown
        size-eos: true
