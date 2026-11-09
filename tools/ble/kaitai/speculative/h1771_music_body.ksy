meta:
  id: h1771_music_body
  title: H1771 candidate onboard music parameters
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H1771 onboard music parameters reconstructed from model
  behaviour, not confirmed by device traffic.  The 0x41 multi-packet upload
  carries the mode followed by this palette and optional mode-specific data.
  Selection and sensitivity are sent separately after the upload.
  Unrecognised suffixes remain opaque.
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
    0x04: rhythm
    0xae: expansion
    0x34: piano
    0x48: pulse
    0x51: flowing
    0x49: rolling
types:
  music_tail:
    params:
      - id: mode
        type: u1
        enum: music_mode
    seq:
      - id: style
        type: u1
        if: mode == music_mode::rhythm and _io.size > 0
      - id: unknown_tail
        size-eos: true
