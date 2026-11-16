meta:
  id: h6127_legacy_status_reply
  title: Govee H6127 original whole-device status
  endian: le
  imports:
    - h6125_status_reply
    - h6127_wire_write
    - ../govee_shared
doc: |
  SPECULATIVE H6127 original status. Whole-device colour contains RGB,
  a temperature flag and companion RGB rather than a Kelvin integer.
  Music modes are Energetic 0, Spectrum 1, Rolling 2 and Rhythm 3.
  The current consumer and older colour consumer disagree about whether
  music RGB starts before or after sensitivity; the command-shaped
  interpretation is retained as a candidate, not hardware confirmation.
  Scenes use one-byte selectors; uploaded DIY uses little-endian 16-bit
  selectors and inline DIY reports its one-byte selector.
  Unknown selectors and suffix bytes remain opaque.
  Public exact-model observations also contain mode 0D followed by RGB.
  Its revision and remaining fields are unknown; only that RGB is decoded.
  https://github.com/egold555/Govee-Reverse-Engineering/blob/master/Products/H6127.md
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
        'aa_domain::power': h6125_status_reply::power_body
        'aa_domain::brightness': h6125_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6125_status_reply::version_body
        'aa_domain::hw_version': h6125_status_reply::hw_version_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
  color_mode:
    0x01: music
    0x02: static
    0x03: colour_music
    0x04: scene
    0x07: inline_diy
    0x0a: diy
    0x0d: observed_static
types:
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
            'color_mode::music': h6127_wire_write::legacy_music_selector
            'color_mode::static': h6127_wire_write::whole_device_colour
            'color_mode::colour_music': h6127_wire_write::colour_music
            'color_mode::scene': cm_scene
            'color_mode::inline_diy': cm_inline_diy
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::observed_static': observed_rgb
  observed_rgb:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  cm_scene:
    seq:
      - id: scene_id
        type: u1
      - id: unknown_tail
        size-eos: true
  cm_inline_diy:
    seq:
      - id: code
        type: u1
      - id: unknown_tail
        size-eos: true
