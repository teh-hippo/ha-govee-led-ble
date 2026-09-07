meta:
  id: h66a0_status_reply
  title: H66A0 segment status hypothesis (fixture only)
  endian: le
  imports:
    - /govee_segment_page
    - /govee_common
    - /status_reply
doc: |
  SPECULATIVE H66A0 exact-model status grammar. Captured official-app replies
  establish the common control domains, four-slot segment pages, video state,
  display settings, relative brightness, camera presence and IC/segment probe.
  Pages 2 and 3, physical segment ordering, and unused final-page slot semantics
  remain unqualified; the segment page therefore preserves unused octets.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: status_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'status_domain::power': status_reply::power_body
        'status_domain::brightness': status_reply::brightness_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::firmware': status_reply::version_body
        'status_domain::hardware': status_reply::hw_version_body
        'status_domain::subordinate_20': status_reply::version_body
        'status_domain::subordinate_21': status_reply::version_body
        'status_domain::camera_install': camera_install_body
        'status_domain::ic_segment_count': ic_segment_count_body
        'status_domain::multi_effect': status_reply::multi_effect_body
        'status_domain::segments': govee_segment_page(14, 4, false)
        'status_domain::display_setting': display_setting_body
        'status_domain::relative_brightness': relative_brightness_body
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x20: subordinate_20
    0x21: subordinate_21
    0x32: camera_install
    0x40: ic_segment_count
    0xa3: multi_effect
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
  colour_mode:
    0x00: video
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
  display_setting:
    0x01: video_sensitivity
    0x04: ai_action
    0x06: white_balance
    0x09: ai_update_status
    0x0a: black_screen_detection
    0x0b: black_border_removal
    0x10: ai_filter
    0x11: hdr_effect
    0x13: white_balance_calibrated
types:
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: colour_mode
      - id: mode_body
        size: 16
        type:
          switch-on: mode
          cases:
            'colour_mode::video': video_body
            'colour_mode::static': static_body
            'colour_mode::scene': status_reply::cm_scene
            'colour_mode::diy': govee_common::diy_selector
            'colour_mode::music': govee_common::music_selector
  static_body:
    seq:
      - id: sub
        type: u1
      - id: opaque
        size-eos: true
  video_body:
    seq:
      - id: game_mode
        type: u1
        valid:
          max: 1
      - id: picture_preset
        type: u1
      - id: saturation
        type: u1
        valid:
          max: 100
      - id: sound_effects
        type: u1
        valid:
          max: 1
      - id: reserved
        type: u1
      - id: sound_effects_softness
        type: u1
        valid:
          max: 100
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  camera_install_body:
    seq:
      - id: raw
        size-eos: true
  ic_segment_count_body:
    seq:
      - id: ic_count
        type: u2be
      - id: segment_count
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  display_setting_body:
    seq:
      - id: setting
        type: u1
        enum: display_setting
      - id: len
        type: u1
      - id: payload
        size: len
        type:
          switch-on: setting
          cases:
            'display_setting::black_border_removal': black_border_removal_payload
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  black_border_removal_payload:
    seq:
      - id: is_on
        type: u1
  relative_brightness_body:
    seq:
      - id: selector
        contents: [0x01]
      - id: edge_count
        type: u1
        valid: 0x04
      - id: left_percent
        type: u1
      - id: top_percent
        type: u1
      - id: right_percent
        type: u1
      - id: bottom_percent
        type: u1
      - id: strip_left_percent
        type: u1
      - id: strip_right_percent
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
