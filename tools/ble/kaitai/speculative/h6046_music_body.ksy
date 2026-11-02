meta:
  id: h6046_music_body
  title: Govee H6046 reassembled music parameters
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
doc: |
  H6046.
  Evidence class: exact-model behavioural audit, not device evidence or hardware
  qualification. Known Pact 1/1 and 2/1 admit four companion-backed modes.
  This is reassembled A3 content, not a 20-byte physical packet: the shared
  header gives marker 1 and transport line count, then command 0x41 and mode.
  Physical A3 fragments carry their own XOR envelope.
  Palette count precedes RGB triples and a mode-specific subeffect/style byte.
  Beat admits 2..8 colours (default red, green, blue); Torch 1..8 and Rainbow
  Ring 6..8. Glitter admits 1..8 and a style byte. Default subeffect/style is
  zero; the other three modes also retain their raw zero-default subeffect.
  Default palettes other than Beat contain red, orange (255,127,0), yellow,
  green, blue, cyan and violet (139,0,255); default sensitivity is 99 in the
  separate selector. No H6076 effect codebook is inherited.
  Upload must succeed before the mode/sensitivity selector is sent. The ACK
  echoes mode and places result at offset 3. Status cannot recover this body.
  Unresolved assumptions: nondefault subeffect meanings, suffixes, physical
  rendering and other revisions. Opaque padding is never required to be zero.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: music_mode
    valid:
      any-of: [music_mode::beat, music_mode::torch, music_mode::rainbow_ring, music_mode::glitter]
  - id: palette_count
    type: u1
    valid:
      min: palette_min
      max: 8
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: palette_count
  - id: subeffect
    type: u1
    doc: Raw per-mode subeffect or Glitter style; zero is the audited default.
  - id: unknown_tail
    size-eos: true
instances:
  palette_min:
    value: 'mode == music_mode::beat ? 2 : (mode == music_mode::rainbow_ring ? 6 : 1)'
  palette_max:
    value: 8
  default_subeffect:
    value: 0
  default_sensitivity:
    value: 99
enums:
  music_mode:
    0x49: beat
    0x50: torch
    0x51: rainbow_ring
    0x52: glitter
