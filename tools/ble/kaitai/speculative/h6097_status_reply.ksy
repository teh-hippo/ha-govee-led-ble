meta:
  id: h6097_status_reply
  title: Govee H6097 logical status reply
  endian: le
  imports:
    - h6099_status_reply
    - h6097_control
    - h6097_music_write
    - ../govee_segment_page
doc: |
  SPECULATIVE H6097 support for issue #431.  Power, percent brightness,
  identities, static Kelvin, fourteen-zone pages, physical IC count and video
  settings share the H6099 field layouts.  Ordinary AA41 adds the three-state
  power-on setting.  Music confirms only mode and sensitivity: contradictory
  trailing-byte classification is deliberately not interpreted as observed
  style, fixed colour or uploaded parameters.  Aggregate Kelvin and RGB pages
  do not identify each zone's native-white intent.  Unknown suffixes, actual
  rendering, encrypted transport and revision differences need qualification.
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
        'status_domain::colour_mode': colour_mode_body
        'status_domain::firmware': h6099_status_reply::version_body
        'status_domain::hardware': h6099_status_reply::hardware_version_body
        'status_domain::physical_ic_count': h6099_status_reply::physical_ic_count_body
        'status_domain::subordinate_20': h6099_status_reply::version_body
        'status_domain::subordinate_21': h6099_status_reply::version_body
        'status_domain::display_setting': h6099_status_reply::display_setting_body
        'status_domain::relative_brightness': h6099_status_reply::relative_brightness_body
        'status_domain::segments': govee_segment_page(14, 4, false)
        'status_domain::installation_direction': h6099_status_reply::installation_direction_body
        'status_domain::camera_health': h6099_status_reply::camera_health_body
        'status_domain::power_on_behaviour': h6097_control::power_on_state
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
    0x41: power_on_behaviour
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
types:
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: h6099_status_reply::mode_sel
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'h6099_status_reply::mode_sel::video': h6099_status_reply::video_state
            'h6099_status_reply::mode_sel::music': music_state
            'h6099_status_reply::mode_sel::scene': h6099_status_reply::scene_state
            'h6099_status_reply::mode_sel::diy': h6099_status_reply::diy_state
            'h6099_status_reply::mode_sel::static_colour': h6099_status_reply::static_state
  music_state:
    seq:
      - id: mode
        type: u1
        enum: h6097_music_write::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: false
