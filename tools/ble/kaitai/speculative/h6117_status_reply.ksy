meta:
  id: h6117_status_reply
  title: Govee H6117 speculative AA status envelope
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_shared
    - govee_rgb_segment_page
    - h6102_status_reply
    - h6125_status_reply
doc: |
  H6117 compatibility hypothesis; no identified device replies are available.
  Shared power, raw brightness, firmware, hardware and gradual fields are
  candidates independently of legacy/newer colour and music selectors.
  A2 pages are RGB-only groups of four; A5 pages contain three brightness/RGB
  records. There are at most fifteen logical segments, not fifty.
  Firmware query availability, complete page delivery, static-colour details
  on older controllers and hardware-version prefixes remain unresolved.
  Parser availability does not authorise queries or claim state recovery.
  The hardware prefix is retained rather than asserted. Legacy static bodies,
  unknown modes and all unused tails stay opaque. The last byte is XOR.
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
        'aa_domain::hw_version': hw_version_body
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
    0x0b: legacy_colour
    0x11: legacy_music
    0x13: music
    0x15: static
  legacy_music_mode:
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
            'color_mode::legacy_music': cm_legacy_music
            'color_mode::music': h6102_status_reply::cm_music
  cm_legacy_music:
    seq:
      - id: mode_id
        type: u1
        enum: legacy_music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
        if: mode_id == legacy_music_mode::rhythm
      - id: fixed_colour_flag
        type: u1
        if: is_colour
      - id: rgb
        type: govee_shared::rgb
        if: is_colour and has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
    instances:
      has_fixed_colour:
        value: 'is_colour ? fixed_colour_flag : 0'
      is_colour:
        value: >-
          mode_id == legacy_music_mode::rhythm or mode_id == legacy_music_mode::spectrum or
          mode_id == legacy_music_mode::rolling
      is_legacy:
        value: is_colour or mode_id == legacy_music_mode::energetic
  hw_version_body:
    seq:
      - id: prefix
        type: u1
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
