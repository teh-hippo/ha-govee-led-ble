meta:
  id: h8604_music_write
  title: Govee H8604 onboard-microphone music selector
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE exact-model selector for H8604 protocol revisions 1, 2 and 3.
  Energetic carries only mode and sensitivity. The other modes carry dynamic/calm
  style, one retained reserved byte, an automatic/fixed-colour flag and RGB.
  This describes onboard-microphone mode selection, not phone-microphone
  streaming or a music parameter upload.
seq:
  - id: header
    contents: [0x33, 0x05, 0x13]
  - id: selector
    type: music_selector
    size: 16
  - id: checksum
    type: u1
enums:
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
types:
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
        if: mode_id != music_mode::energetic
        valid:
          any-of: [0, 1]
      - id: reserved
        contents: [0]
        if: mode_id != music_mode::energetic
      - id: has_fixed_colour
        type: u1
        if: mode_id != music_mode::energetic
        valid:
          any-of: [0, 1]
      - id: rgb
        type: govee_shared::rgb
        if: mode_id != music_mode::energetic
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: mode_id != music_mode::energetic
