meta:
  id: h8604_status_reply
  title: Govee H8604 status overlay
  endian: le
  imports:
    - ../govee_shared
    - ../govee_segment_page
    - h60a_bulk
    - h6099_status_reply
    - h8604_video_settings
doc: |
  SPECULATIVE exact H8604 status contract for protocol revisions 1, 2 and 3.
  Ordinary controls, fourteen-zone pages, video and display settings reuse the
  H6099 layout. Music keeps the H8604 reserved byte between style and automatic
  colour. Power-on behaviour and gradual state use their native 0x41 and 0xa3
  replies. Unknown suffixes remain opaque.
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
        'status_domain::power': h6099_status_reply::power_body
        'status_domain::brightness': h6099_status_reply::brightness_body
        'status_domain::firmware': h6099_status_reply::version_body
        'status_domain::hardware': hardware_body
        'status_domain::subordinate_20': h6099_status_reply::version_body
        'status_domain::subordinate_21': h6099_status_reply::version_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::display_setting': h8604_video_settings::setting_body
        'status_domain::relative_brightness': h6099_status_reply::relative_brightness_body
        'status_domain::segments': govee_segment_page(14, 4, false)
        'status_domain::installation_direction': h6099_status_reply::installation_direction_body
        'status_domain::physical_ic_count': h6099_status_reply::physical_ic_count_body
        'status_domain::power_on_behaviour': power_on_body
        'status_domain::gradual': gradual_body
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
    0x30: installation_direction
    0x40: physical_ic_count
    0x41: power_on_behaviour
    0xa3: gradual
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
  mode_sel:
    0x00: video
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static_colour
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
  hardware_selector:
    0x03: version
    0x08: device_info
types:
  hardware_body:
    seq:
      - id: selector
        type: u1
        enum: hardware_selector
      - id: detail
        size: 16
        type:
          switch-on: selector
          cases:
            'hardware_selector::version': hardware_version
            'hardware_selector::device_info': device_info
    instances:
      text:
        value: detail.as<hardware_version>.text
        if: selector == hardware_selector::version
  hardware_version:
    seq:
      - id: text
        type: strz
        encoding: ASCII
  device_info:
    seq:
      - id: reserved
        type: u1
      - id: source_mask
        type: u1
      - id: box_light_enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: box_brightness
        type: u1
      - id: box_auto
        type: u1
        valid:
          any-of: [0, 1]
      - id: box_effect
        type: u1
      - id: logo_auto
        type: u1
        valid:
          any-of: [0, 1]
      - id: logo_brightness
        type: u1
      - id: logo_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_sel::video': h6099_status_reply::video_state
            'mode_sel::music': music_state
            'mode_sel::scene': h6099_status_reply::scene_state
            'mode_sel::diy': h6099_status_reply::diy_state
            'mode_sel::static_colour': h6099_status_reply::static_state
  music_state:
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
        valid:
          max: 99
      - id: is_calm
        type: u1
        if: mode != music_mode::energetic
        valid:
          any-of: [0, 1]
      - id: reserved
        contents: [0]
        if: mode != music_mode::energetic
      - id: has_fixed_colour
        type: u1
        if: mode != music_mode::energetic
        valid:
          any-of: [0, 1]
      - id: fixed_colour
        type: govee_shared::rgb
        if: mode != music_mode::energetic
      - id: unknown_tail
        size-eos: true
  power_on_body:
    seq:
      - id: availability
        type: u1
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
  gradual_body:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
