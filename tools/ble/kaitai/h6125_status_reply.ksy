meta:
  id: h6125_status_reply
  title: Govee H6125 "aa" status-reply envelope
  endian: le
  imports:
    - govee_shared
doc: |
  H6125 20-byte status reply for the pact-1 controller branch. The final byte
  is the XOR of bytes 0 through 18. Unknown mode tails remain opaque.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: aa_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'aa_domain::power': power_body
        'aa_domain::brightness': brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::segments': segments_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa1: a1_terminal
    0xa3: a3_terminal
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x0b: legacy_static
    0x0c: legacy_music
    0x11: music_v1
    0x13: music_v3
    0x15: static
    0x16: dynamic
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
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: tail
        size-eos: true
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
      - id: tail
        size-eos: true
  colormode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: mode_body
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::static': static_body
            'color_mode::scene': selector_body
            'color_mode::diy': selector_body
            'color_mode::music_v1': music_body
            'color_mode::music_v3': music_body
  static_body:
    seq:
      - id: gradual
        type: u1
      - id: kelvin
        type: u2be
      - id: tail
        size-eos: true
  selector_body:
    seq:
      - id: code
        type: u2le
      - id: tail
        size-eos: true
  music_body:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'music_mode::rhythm': rhythm_settings
            'music_mode::spectrum': colour_settings
            'music_mode::rolling': colour_settings
  rhythm_settings:
    seq:
      - id: style
        type: u1
      - id: manual_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_colour != 0
      - id: tail
        size-eos: true
  colour_settings:
    seq:
      - id: manual_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_colour != 0
      - id: tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: tail
        size-eos: true
  hw_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: tail
        size-eos: true
  segments_body:
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 5
      - id: segments
        type: segment
        repeat: expr
        repeat-expr: 3
      - id: tail
        size-eos: true
  segment:
    seq:
      - id: brightness
        type: u1
      - id: colour
        type: govee_shared::rgb
