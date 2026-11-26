meta:
  id: h6102_legacy_status_reply
  title: Govee H6102 Pact 1 legacy AA status replies
  endian: le
  imports:
    - ../govee_shared
    - h6102_status_reply
doc: |
  H6102.
  Pact 1 revisions report static colour with mode 02. The payload carries RGB,
  a temperature flag and companion RGB. Music is reported with mode 01, the
  original 0/3/1/2 selector codebook, sensitivity, and direct RGB only for
  Spectrum and Rolling. Scene and DIY selectors remain independently readable.
  Unknown tails stay opaque.
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
        'aa_domain::power': h6102_status_reply::power_body
        'aa_domain::brightness': h6102_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': h6102_status_reply::hw_version_body
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
    0x04: scene
    0x0a: diy
  music_mode:
    0: energetic
    3: rhythm
    1: spectrum
    2: rolling
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
            'color_mode::music': cm_music
            'color_mode::static': cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
  cm_static:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: temperature_flag
        type: u1
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  cm_music:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: mode_id == music_mode::spectrum or mode_id == music_mode::rolling
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: true
      has_fixed_colour:
        value: mode_id == music_mode::spectrum or mode_id == music_mode::rolling
