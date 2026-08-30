meta:
  id: h6125_music_write
  title: Govee H6125 pact-1 music selector
  endian: le
  imports:
    - govee_shared
doc: |
  H6125 pact-1 20-byte music selector. Expanded modes use this selector before
  their A3 command-0x41 parameter body.
seq:
  - id: header
    contents: [0x33, 0x05, 0x11]
  - id: mode
    type: u1
    enum: music_mode
  - id: sensitivity
    type: u1
  - id: settings
    size: 14
    type:
      switch-on: mode
      cases:
        'music_mode::rhythm': rhythm_settings
        'music_mode::spectrum': colour_settings
        'music_mode::rolling': colour_settings
        _: empty_settings
  - id: checksum
    type: u1
enums:
  music_mode:
    0x10: energetic
    0x11: rhythm
    0x12: spectrum
    0x13: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
types:
  empty_settings:
    seq:
      - id: padding
        size-eos: true
  rhythm_settings:
    seq:
      - id: style
        type: u1
      - id: manual_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_colour != 0
      - id: padding
        size-eos: true
  colour_settings:
    seq:
      - id: manual_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_colour != 0
      - id: padding
        size-eos: true
