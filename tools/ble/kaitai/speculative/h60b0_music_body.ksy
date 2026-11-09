meta:
  id: h60b0_music_body
  title: H60B0 onboard music parameters
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H60B0 onboard-microphone companion, not hardware-confirmed.
  A3 subtype 41 carries mode and parameters. Activation is 33 05 13,
  mode and sensitivity. Combined mode 130 has side then ripple sections;
  section lengths exclude each mode/length pair. Hopping piece budgets
  depend on the physical IC count, not the nine logical colour positions.
  Unknown suffix bytes remain unqualified and are retained.
seq:
  - id: mode
    type: u1
    enum: music_mode
  - id: body
    type:
      switch-on: mode
      cases:
        'music_mode::combined': combined_parameters
        _: parameters(mode)
types:
  combined_parameters:
    seq:
      - id: side
        type: zone
      - id: ripple
        type: zone
      - id: unknown_tail
        size-eos: true
  zone:
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: len_parameters
        type: u1
      - id: body
        type: parameters(mode)
        size: len_parameters
  parameters:
    params:
      - id: mode
        type: u1
        enum: music_mode
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
            'music_mode::hopping': hopping_parameters
            'music_mode::bloom': style_parameters
            'music_mode::shiny': style_parameters
            _: opaque_parameters
  style_parameters:
    seq:
      - id: style
        type: u1
        enum: style
      - id: unknown_tail
        size-eos: true
  hopping_parameters:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: relative_brightness
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
      - id: unknown_tail
        size-eos: true
enums:
  music_mode:
    0: disabled
    48: bloom
    49: shiny
    51: hopping
    80: vortex
    81: firefly
    83: flow
    114: rhythm
    130: combined
    131: spectrum
  style:
    0: dynamic
    1: calm
