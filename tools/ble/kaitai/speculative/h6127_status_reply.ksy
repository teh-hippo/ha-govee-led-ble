meta:
  id: h6127_status_reply
  title: Govee H6127 extended Telink status
  endian: le
  imports:
    - h6125_status_reply
    - h6102_status_reply
    - h6127_legacy_status_reply
    - ../govee_segment_page
doc: |
  SPECULATIVE H6127 extended Telink status. Static colour, scene, DIY,
  music and identity bodies use the compatible DreamColor layouts.
  Gradual uses register 14; segment pages contain three brightness/RGB
  records. Eligibility requires the exact product's revision policy.
  Physical readback and unused bytes remain unconfirmed.
  Mode 0D retains the narrow original RGB observation with no inferred
  white fields or revision boundary.
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
    0x14: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x0d: observed_static
    0x11: music
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
            'color_mode::static': h6125_status_reply::cm_static
            'color_mode::scene': h6125_status_reply::cm_scene
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::music': h6125_status_reply::cm_music
            'color_mode::observed_static': h6127_legacy_status_reply::observed_rgb
