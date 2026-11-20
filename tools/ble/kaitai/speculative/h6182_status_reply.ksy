meta:
  id: h6182_status_reply
  title: Govee H6182 legacy whole-strip status
  endian: be
  imports:
    - h6181_status_reply
    - h6159_wire_write
doc: |
  SPECULATIVE H6182 legacy status. Owner reports include mode 02 with
  the applied RGB and mode 0D with black after an ineffective colour write.
  Both colour selectors report RGB, a temperature flag and companion RGB,
  not a Kelvin integer. Music mode 03 reports fixed-colour flag,
  sensitivity and optional RGB, without a separate effect selector.
  Version replies contain ASCII strings. Unknown bytes remain opaque.
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
enums:
  color_mode:
    0x02: legacy_colour
    0x03: music
    0x04: scene
    0x0a: diy
    0x0d: static_colour
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
            'color_mode::static_colour': h6181_status_reply::static_colour_body
            'color_mode::scene': h6181_status_reply::scene_body
            'color_mode::diy': h6181_status_reply::diy_body
            'color_mode::music': h6159_wire_write::legacy_music_body
