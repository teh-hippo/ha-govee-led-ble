meta:
  id: h6199_status_reply
  title: Govee H6199 "aa" status-reply envelope (decode-only)
  endian: le
  imports:
    - govee_shared
doc: |
  H6199 20-byte status reply. The final byte is the XOR of bytes 0 through 18.
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
        'status_domain::segments': segment_group_body
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x06: firmware
    0x07: hardware
    0x05: colour_mode
    0x20: subordinate_20
    0x21: subordinate_21
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
  mode_sel:
    0x00: video
    0x04: scene
    0x13: music
    0x15: static_colour
  video_source:
    0x00: movie
    0x01: game
  video_region:
    0x00: part
    0x01: all
types:
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
            'display_setting::blank_screen': blank_screen_state
      - id: padding
        type: u1
        valid: 0
        repeat: eos
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
  blank_screen_state:
    seq:
      - id: is_enabled
        type: u1
      - contents: [0x02, 0x0a, 0x00, 0x78, 0x00]
  relative_brightness_body:
    seq:
      - id: selector
        contents: [0x01]
      - id: edge_count
        contents: [0x04]
      - id: left_percent
        type: u1
      - id: top_percent
        type: u1
      - id: right_percent
        type: u1
      - id: bottom_percent
        type: u1
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
            'mode_sel::video': video_state
            'mode_sel::music': music_state
            'mode_sel::scene': scene_state
  music_state:
    seq:
      - id: mode
        type: u1
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: fixed_colour
        type: govee_shared::rgb
  video_state:
    seq:
      - id: region
        type: u1
        enum: video_region
      - id: source
        type: u1
        enum: video_source
      - id: saturation
        type: u1
      - id: sound_effects
        type: u1
      - id: softness
        type: u1
  scene_state:
    seq:
      - id: scene_id
        type: u2le
  power_body:
    seq:
      - id: is_on
        type: u1
  brightness_body:
    seq:
      - id: percent
        type: u1
  segment_record:
    seq:
      - id: brightness_percent
        type: u1
      - id: colour
        type: govee_shared::rgb
  segment_group_body:
    seq:
      - id: group
        type: u1
      - id: segments
        type: segment_record
        repeat: expr
        repeat-expr: 'group == 4 ? 3 : 4'
      - size: 4
        if: group == 4
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
  hardware_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
