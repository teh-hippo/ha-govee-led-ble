meta:
  id: h6072_status_reply
  title: H6072 candidate basic and eight-zone status
  endian: le
  imports:
    - ../govee_segment_page
    - govee_rgb_segment_page
    - h6076_status_reply
    - h6076_music_write
    - h6102_status_reply
doc: |
  H6072.
  Compatibility hypothesis: common basic and mode records, with eight logical
  zones in three-record pages. Legacy A2 pages contain RGB only; newer A5
  pages contain brightness and RGB. Static replies need not echo RGB or Kelvin.
  Receive recognition does not authorise a revision-specific writer.
  Complete owner frames, unused slots and revision-specific timing remain unqualified.
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
        'aa_domain::brightness': h6076_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': h6102_status_reply::hw_version_body
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::legacy_segments': govee_rgb_segment_page(8, 3)
        'aa_domain::segments': govee_segment_page(8, 3, false)
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
    0x04: scene
    0x0a: diy
    0x0f: music
    0x14: legacy_static
    0x15: static
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
            'color_mode::legacy_static': h6102_status_reply::cm_static
            'color_mode::static': h6102_status_reply::cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::music': h6076_music_write::music_selector
