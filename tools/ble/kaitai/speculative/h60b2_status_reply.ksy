meta:
  id: h60b2_status_reply
  title: H60B2 candidate ordinary and three-head status
  endian: le
  imports:
    - ../govee_segment_page
    - h6102_status_reply
    - h607c_control
    - h60b2_control
    - h60b2_music_body
doc: |
  SPECULATIVE: Exact-product ordinary replies and three-record A5 pages.
  AA05 static replies identify mode, not RGB; an all-zero payload does not
  establish black output or Kelvin. Hardware identity is optional and may be
  unanswered. Source power is separate from master power and colour pages.
  Unknown modes and suffixes remain opaque.
  Music readback uses 0x0f independently of the 0x13 write selector.
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
        'aa_domain::brightness': brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': h6102_status_reply::hw_version_body
        'aa_domain::zone_enable': h60b2_control::source_state
        'aa_domain::power_on_behaviour': h607c_control::power_on_state
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::segments': govee_segment_page(3, 3, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x36: zone_enable
    0x41: power_on_behaviour
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x0f: music
    0x15: static
types:
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
      - id: unknown_tail
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
            'color_mode::static': h6102_status_reply::cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::music': music_selector
  music_selector:
    seq:
      - id: mode
        type: u1
        enum: h60b2_music_body::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: false
