meta:
  id: h605c_music_write
  title: H605C onboard music selectors
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE exact-model onboard-microphone music contract for both registered
  Pact revisions. Energetic uses only selector and sensitivity; the other
  three modes carry style and colour fields. Rhythm exposes the style control.
  Style 0 means dynamic and 1 calm. Colour flag 0 means automatic and 1 fixed.
  The shared selector codec implements this layout; no music-parameter upload
  is required. Sensitivity is 0..99. This does not describe phone-mic streaming.
  Suffix bytes remain opaque. The checksum is XOR of the preceding 19 bytes.
seq:
  - id: header
    contents: [0x33, 0x05, 0x13]
  - id: body
    type: music
    size: 16
  - id: checksum
    type: u1
enums:
  mode:
    3: rhythm
    4: spectrum
    5: energetic
    6: rolling
types:
  music:
    seq:
      - id: mode
        type: u1
        enum: mode
      - id: sensitivity
        type: u1
      - id: calm
        type: u1
        if: mode != mode::energetic
      - id: fixed_colour
        type: u1
        if: mode != mode::energetic
      - id: colour
        type: govee_shared::rgb
        if: mode != mode::energetic
      - id: unknown_tail
        size-eos: true
