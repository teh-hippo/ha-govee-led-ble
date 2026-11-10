meta:
  id: h6181_modern_status_reply
  title: Govee H6181 later-revision status
  endian: be
  imports:
    - ../govee_shared
    - h6181_status_reply
doc: |
  SPECULATIVE H6181 later Pact >=10/1 status. Ordinary colour carries
  RGB, Kelvin BE16 and companion RGB, unlike legacy flag-based readback.
  Music readback routes disagree about selector and style positions, so
  these fields retain neutral names until qualified on hardware.
  Opaque suffixes are retained; status and accepted writes are independent.
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
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x13: music
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
            'color_mode::static_colour': static_colour_body
            'color_mode::scene': h6181_status_reply::scene_body
            'color_mode::diy': h6181_status_reply::diy_body
            'color_mode::music': music_body
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  music_body:
    seq:
      - id: observed_selector
        type: u1
      - id: sensitivity
        type: u1
      - id: observed_style
        type: u1
      - id: colour_mode
        type: u1
      - id: stored_colour
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
