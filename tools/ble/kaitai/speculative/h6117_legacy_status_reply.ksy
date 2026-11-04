meta:
  id: h6117_legacy_status_reply
  title: Govee H6117 speculative legacy music status replies
  endian: le
  imports:
    - h6117_status_reply
    - h6125_status_reply
    - h6102_status_reply
    - govee_rgb_segment_page
    - ../govee_segment_page
doc: |
  H6117 compatibility hypothesis, not captured replies.
  The legacy music selector is 0x11 with the 0x10..0x13 basic codebook;
  it is not H6125's original 0x0c codebook. Static mode can be whole-device
  0x02, RGB-only 0x0b or extended 0x15. Older static details stay opaque.
  Candidate A2/A5 pages do not establish query availability or restoration.
  Hardware prefixes and unknown suffixes are retained without zero checks.
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
        'aa_domain::hw_version': h6117_status_reply::hw_version_body
        'aa_domain::legacy_segments': govee_rgb_segment_page(15, 4)
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::segments': govee_segment_page(15, 3, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa2: legacy_segments
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x02: whole_device_colour
    0x04: scene
    0x0a: diy
    0x0b: legacy_static
    0x11: music
    0x15: static
  music_mode:
    0x10: energetic
    0x11: rhythm
    0x12: rolling
    0x13: spectrum
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
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
            'color_mode::static': h6125_status_reply::cm_static
            'color_mode::scene': h6125_status_reply::cm_scene
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::music': h6117_status_reply::cm_legacy_music
