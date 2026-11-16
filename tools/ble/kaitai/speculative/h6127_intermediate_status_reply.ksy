meta:
  id: h6127_intermediate_status_reply
  title: Govee H6127 intermediate Telink status
  endian: le
  imports:
    - h6125_status_reply
    - h6125_intermediate_status_reply
    - h6102_status_reply
    - h6127_legacy_status_reply
    - h6125_legacy_status_reply
    - govee_rgb_segment_page
doc: |
  SPECULATIVE H6127 DreamColor status before extended colour eligibility.
  Colour uses submode 0B, music 11, and scene/DIY selectors are little-endian
  16-bit. A2 pages contain four RGB-only records and gradual uses register
  14. Physical readback, reply presence and opaque bytes need confirmation.
  Mode 0D preserves the narrow original H6127 RGB observation without
  assigning its unknown hardware/firmware revision to this route.
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
        'aa_domain::segments': govee_rgb_segment_page(15, 4)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x14: multi_effect
    0xa2: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x0b: static
    0x0d: observed_static
    0x11: music
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
            'color_mode::static': h6125_legacy_status_reply::cm_static
            'color_mode::scene': h6125_intermediate_status_reply::cm_scene
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::music': h6125_status_reply::cm_music
            'color_mode::observed_static': h6127_legacy_status_reply::observed_rgb
