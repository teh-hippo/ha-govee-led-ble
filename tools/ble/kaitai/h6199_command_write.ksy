meta:
  id: h6199_command_write
  title: Govee H6199 "33" command-write envelope (decode-only)
  endian: le
  imports:
    - govee_shared
doc: |
  H6199 20-byte command frame. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
        'command_op::display_setting': display_setting_body
        'command_op::relative_brightness': relative_brightness_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0xa9: display_setting
    0xae: relative_brightness
  mode_sel:
    0x00: video
    0x04: scene
    0x15: static_colour
    0x13: music
  video_source:
    0x00: movie
    0x01: game
  video_region:
    0x00: part
    0x01: all
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
  static_operation:
    0x01: colour
    0x02: brightness
types:
  power_body:
    seq:
      - id: is_on
        type: u1
  brightness_body:
    seq:
      - id: percent
        type: u1
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::video': video_body
            'mode_sel::scene': scene_body
            'mode_sel::static_colour': static_colour_body
            'mode_sel::music': music_body
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: music_code
        type: u2le
  video_body:
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
      - id: relative_brightness_percent
        type: u1
        valid:
          max: 100
  relative_brightness_body:
    seq:
      - id: selector
        contents: [0x01]
      - id: edge_count
        type: u1
      - id: left_percent
        type: u1
      - id: top_percent
        type: u1
      - id: right_percent
        type: u1
      - id: bottom_percent
        type: u1
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
            'display_setting::white_balance': white_balance_payload
            'display_setting::blank_screen': blank_screen_payload
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  white_balance_payload:
    seq:
      - id: manual
        type: u1
      - id: red
        type: u1
      - id: blue
        type: u1
  blank_screen_payload:
    seq:
      - id: is_on
        type: u1
      - contents: [0x02, 0x0a, 0x00, 0x78, 0x00]
  music_body:
    seq:
      - id: mode
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: fixed_colour
        type: govee_shared::rgb
  static_colour_body:
    seq:
      - id: operation
        type: u1
        enum: static_operation
      - id: red
        type: u1
        if: operation == static_operation::colour
      - id: green
        type: u1
        if: operation == static_operation::colour
      - id: blue
        type: u1
        if: operation == static_operation::colour
      - id: kelvin
        type: u2be
        if: operation == static_operation::colour
      - id: preview
        type: govee_shared::rgb
        if: operation == static_operation::colour
      - id: segment_mask
        type: u2
        if: operation == static_operation::colour
      - id: brightness_percent
        type: u1
        if: operation == static_operation::brightness
      - id: brightness_segment_mask
        type: u2
        if: operation == static_operation::brightness
