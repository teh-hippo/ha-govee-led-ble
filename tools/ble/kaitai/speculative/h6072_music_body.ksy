meta:
  id: h6072_music_body
  title: H6072 candidate onboard music companion
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h6076_music_body
    - h617a_control_payload
doc: |
  H6072.
  Compatibility hypothesis: A3 subtype 41 carries a mode and palette.
  Separation adds split point, gradient and a topology-dependent companion.
  The declared lamp geometry selects the long-strip companion, independently
  of the eight logical colour zones. Owner captures and ACK timing are unqualified.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: h6076_music_body::music_mode
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
        'h6076_music_body::music_mode::separation': h617a_control_payload::separation_tail
  - id: padding
    size-eos: true
instances:
  tail_len:
    value: 'mode == h6076_music_body::music_mode::separation ? 3 : 0'
