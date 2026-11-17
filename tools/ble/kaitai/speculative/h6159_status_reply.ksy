meta:
  id: h6159_status_reply
  title: Govee H6159 whole-strip status
  endian: be
  imports:
    - h6181_command_write
    - h6181_status_reply
    - h6181_modern_status_reply
    - h6159_wire_write
doc: |
  SPECULATIVE H6159 status, awaiting recorded device traffic.
  Mode 02 reports RGB, temperature flag and companion RGB. Mode 0D uses
  RGB, Kelvin BE16 and companion RGB. Identity strings are ASCII.
  Onboard music uses mode 03 before firmware 1.03.00 and mode 0E later;
  the later Pact route uses mode 13. Palette parameters are not read back.
  Brightness scaling is selected by the effective product revision.
  Unknown bytes are retained without invented padding validation.
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
        'aa_domain::power': h6181_status_reply::power_body
        'aa_domain::brightness': h6181_status_reply::brightness_body
        'aa_domain::colour_mode': colour_mode_body
        'aa_domain::firmware': h6181_status_reply::version_body
        'aa_domain::hardware': h6181_status_reply::hardware_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
  color_mode:
    0x02: legacy_colour
    0x03: legacy_music
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x0e: music
    0x13: modern_music
types:
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::legacy_colour': h6181_status_reply::static_colour_body
            'color_mode::static_colour': h6181_modern_status_reply::static_colour_body
            'color_mode::scene': h6181_status_reply::scene_body
            'color_mode::diy': h6181_status_reply::diy_body
            'color_mode::legacy_music': h6159_wire_write::legacy_music_body
            'color_mode::music': h6159_wire_write::music_body
            'color_mode::modern_music': h6181_command_write::music_body
