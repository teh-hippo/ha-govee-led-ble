meta:
  id: h60b2_music_body
  title: H60B2 candidate onboard music companions
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: Seven independently declared onboard modes. The upload contains
  mode, counted RGB palette and mode-specific companions; sensitivity follows
  in the separate 0x13 selector. Hopping has background RGB and brightness
  rather than strip-geometry parameters. Style is dynamic zero or calm one.
  Unknown suffixes remain opaque; hardware rendering is unconfirmed.
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
    size-eos: true
    type: music_tail(mode)
enums:
  music_mode:
    131: spectrum
    75: rhythm
    72: hopping
    99: energetic
    81: firefly
    73: rolling
    67: bloom
  style:
    0: dynamic
    1: calm
types:
  music_tail:
    params:
      - id: mode
        type: u1
        enum: music_mode
    seq:
      - id: style
        type: u1
        enum: style
        if: mode == music_mode::rhythm or mode == music_mode::bloom
      - id: background
        type: govee_shared::rgb
        if: mode == music_mode::hopping
      - id: relative_brightness
        type: u1
        if: mode == music_mode::hopping
      - id: unknown_tail
        size-eos: true
