meta:
  id: h6125_legacy_status_reply
  title: Govee H6125 legacy RGB-only status replies
  endian: le
  imports:
    - h6125_status_reply
    - h6102_status_reply
    - govee_rgb_segment_page
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: legacy controllers use submode 0x0b colour and
  A2 RGB-only pages. The original H612526 route uses submode 0x0c music.
  Application consumers establish these layouts, not firmware acceptance.
  Unresolved assumptions: per-revision reply presence, unused bytes and
  legacy scene catalogue availability. Colour mode does not report RGB.
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
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::segments': govee_rgb_segment_page(15)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa2: segments
    0xa3: multi_effect
  color_mode:
    0x04: scene
    0x0a: diy
    0x0b: static
    0x0c: music
  music_mode:
    0x00: energetic
    0x04: rhythm
    0x03: spectrum
    0x02: rolling
  scene_mode:
    4: film
    5: date
    7: romantic
    8: blinking
    9: candle
    10: breathe
    15: snow
    16: energetic
    21: chase
    22: stream
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
            'color_mode::static': cm_static
            'color_mode::scene': cm_scene
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::music': cm_music
  cm_static:
    seq:
      - id: sub
        type: u1
      - id: unknown_tail
        size-eos: true
  cm_scene:
    seq:
      - id: scene_id
        type: u1
        enum: scene_mode
      - id: unknown_tail
        size-eos: true
  cm_music:
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
            'music_mode::energetic': h6125_status_reply::opaque_settings
            _: h6125_status_reply::colour_settings
    instances:
      is_legacy:
        value: true
      style:
        value: 0
      has_fixed_colour:
        value: 'mode_id == music_mode::energetic ? 0 : settings.as<h6125_status_reply::colour_settings>.has_fixed_colour'
      rgb:
        value: settings.as<h6125_status_reply::colour_settings>.rgb
