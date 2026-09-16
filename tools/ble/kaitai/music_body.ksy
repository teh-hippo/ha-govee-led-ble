meta:
  id: music_body
  title: Govee H617A music-mode wire structures
  endian: le
  imports:
    - govee_shared
    - govee_common
    - speculative/h617a_control_payload
doc: >
  Capture-backed H617A music envelope and presets. Generalized APK-backed tails
  remain in speculative/h617a_control_payload.ksy under issue #286 (Fountain #129);
  importing them does not promote their evidence class. Palette-relative tails are
  read and written by the generated adapter. A structurally valid alternative
  palette or tail does not qualify model-specific bounds, defaults, style,
  companion values, or physical IC geometry. Issue 286 synthetic tests reuse
  this structure without claiming new device support.
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
        'govee_common::music_mode::bloom': h617a_control_payload::bloom_tail
        'govee_common::music_mode::shiny': h617a_control_payload::shiny_tail
        'govee_common::music_mode::separation': h617a_control_payload::separation_tail
        'govee_common::music_mode::hopping': h617a_control_payload::hopping_tail
        'govee_common::music_mode::piano_keys': h617a_control_payload::piano_keys_tail
        'govee_common::music_mode::fountain': h617a_control_payload::fountain_tail
        'govee_common::music_mode::day_and_night': h617a_control_payload::day_and_night_tail
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
  mode_set_frame:
    seq:
      - id: header
        contents: [0x33]
      - id: domain
        contents: [0x05]
      - id: sub
        contents: [0x13]
      - id: selector
        size: 16
        type: govee_common::music_selector
      - id: checksum
        type: u1
