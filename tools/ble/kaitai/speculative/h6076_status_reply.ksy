meta:
  id: h6076_status_reply
  title: Govee H6076 basic, segment, gradual and music status
  endian: le
  imports:
    - ../govee_segment_page
    - h6076_music_write
    - h6102_status_reply
doc: |
  SPECULATIVE H6076, issue #401.
  In Android 7.6.01, H6076 (goods type 69) uses the shared power, percentage
  brightness, firmware, hardware, and gradual (0xa3) status layouts, dispatches
  AA05 mode 15 to static colour/Kelvin, 04 to scenes, 0A to DIY, and 0F to
  music state, and reads A5 segment pages of four brightness/RGB records across
  seven logical segments in two groups.  Owner logs in issues #112 and #247
  confirm AA01, AA04, AA05 15, AA06, AA07, and AAA5 group 2 on physical H6076
  hardware; music replies follow the 0x0f selector layout from issue #343.
  Common payload imports do not inherit H6102's product capabilities.
  Unknown modes, suffixes, and unused bytes remain opaque.
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
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::segments': govee_segment_page(7, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
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
            'color_mode::music': h6076_music_write::music_selector
