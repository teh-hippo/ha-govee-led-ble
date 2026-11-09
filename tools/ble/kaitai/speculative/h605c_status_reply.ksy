meta:
  id: h605c_status_reply
  endian: le
  imports:
    - ../govee_shared
    - ../govee_segment_page
    - h605c_video_command
doc: |
  SPECULATIVE exact H605C status. A5 exposes 14 logical records in four pages.
  Wireless identity 20 is hardware and 21 is firmware. Ordinary video replies
  use the long video layout independently of protocol revision. Static mode
  establishes only its selector; grouped colour reads carry actual colours.
  Unknown suffix bytes remain opaque. No calibration runtime is implemented.
  Music status retains style and colour fields for all four selectors;
  Energetic's short write does not imply a short status response.
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
        'status_domain::power': power_body
        'status_domain::brightness': brightness_body
        'status_domain::firmware': version_body
        'status_domain::hardware': hardware_version_body
        'status_domain::subordinate_20': version_body
        'status_domain::subordinate_21': version_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::display_setting': display_setting_body
        'status_domain::relative_brightness': relative_brightness_body
        'status_domain::segments': govee_segment_page(14, 4, false)
        'status_domain::gradual': gradual_body
        'status_domain::installation_direction': installation_direction_body
        'status_domain::camera_health': camera_health_body
        'status_domain::physical_ic_count': physical_ic_count_body
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
    0x32: camera_health
    0x40: physical_ic_count
    0xa5: segments
    0xa3: gradual
    0xa9: display_setting
    0xae: relative_brightness
  display_setting:
    0x00: white_balance
    0x02: whole_relative_brightness
    0x0a: blank_screen
  blank_screen_detection:
    1: low_brightness
    2: same_tone
  camera_health:
    0: absent
    1: healthy
    2: incompatible
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
types:
  installation_direction_body:
    seq:
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  camera_health_body:
    seq:
      - id: value
        type: u1
        enum: camera_health
      - id: unknown_tail
        size-eos: true
  physical_ic_count_body:
    seq:
      - id: count
        type: s2be
      - id: unknown_tail
        size-eos: true
  gradual_body:
    seq:
      - id: flag
        type: u1
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
            'mode_sel::video': h605c_video_command::video_body
            'mode_sel::music': music_state
            'mode_sel::scene': scene_state
            'mode_sel::diy': diy_state
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
        valid:
          any-of: [0, 1]
      - id: has_fixed_colour
        type: u1
        valid:
          any-of: [0, 1]
      - id: fixed_colour
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: true
  scene_state:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  diy_state:
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
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
            'display_setting::white_balance': white_balance_state
            'display_setting::whole_relative_brightness': whole_brightness_state
            'display_setting::blank_screen': blank_screen_state
      - id: unknown_tail
        size-eos: true
  whole_brightness_state:
    seq:
      - id: value
        type: u1
        valid:
          max: 100
      - id: unknown_tail
        size-eos: true
  white_balance_state:
    seq:
      - id: reset_flag
        type: u1
      - id: reset_red
        type: u1
      - id: reset_blue
        type: u1
      - id: current_flag
        type: u1
      - id: current_red
        type: u1
      - id: current_blue
        type: u1
      - id: unknown_tail
        size-eos: true
  blank_screen_state:
    seq:
      - id: is_enabled
        type: u1
      - id: detection
        type: u1
        enum: blank_screen_detection
      - id: low_brightness_duration_seconds
        type: u2
      - id: same_tone_duration_seconds
        type: u2
      - id: unknown_tail
        size-eos: true
  relative_brightness_body:
    seq:
      - id: selector
        contents: [1]
      - id: edge_count
        type: u1
        valid: 4
      - id: left_percent
        type: u1
      - id: top_percent
        type: u1
      - id: right_percent
        type: u1
      - id: bottom_percent
        type: u1
      - id: unknown_tail
        size-eos: true
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  hardware_version_body:
    seq:
      - id: prefix
        contents: [3]
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
