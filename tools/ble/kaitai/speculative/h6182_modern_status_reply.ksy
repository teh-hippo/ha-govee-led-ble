meta:
  id: h6182_modern_status_reply
  title: Govee H6182 later-controller whole-strip status
  endian: be
  imports:
    - h6181_status_reply
    - h6181_modern_status_reply
doc: |
  SPECULATIVE H6182 later Pact status, awaiting recorded device traffic.
  Mode 0D reports RGB, Kelvin BE16 and companion RGB; mode 02 retains
  the temperature-flag colour-effect shape. Music mode 13 carries the
  independently qualified dynamic, soft or palette selector.
  Brightness scaling follows hardware identity, not the status envelope.
  Unknown fields remain opaque.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: h6181_status_reply::aa_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'h6181_status_reply::aa_domain::power': h6181_status_reply::power_body
        'h6181_status_reply::aa_domain::brightness': h6181_status_reply::brightness_body
        'h6181_status_reply::aa_domain::colour_mode': colour_mode_body
        'h6181_status_reply::aa_domain::firmware': h6181_status_reply::version_body
        'h6181_status_reply::aa_domain::hardware': h6181_status_reply::hardware_body
  - id: checksum
    type: u1
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
            'color_mode::music': h6181_modern_status_reply::music_body
enums:
  color_mode:
    0x02: legacy_colour
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x13: music
