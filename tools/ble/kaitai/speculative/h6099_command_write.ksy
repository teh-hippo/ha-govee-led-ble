meta:
  id: h6099_command_write
  title: Govee H6099 "33" command-write envelope
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6099 20-byte command frame for issue #258.
  The final byte is the XOR of bytes 0 through 18.

  The structure is derived from the official app's H6099 product path and remains
  speculative until exact-model owner qualification. Unknown padding is preserved.
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
    0x08: part
    0x09: all
  display_setting:
    0x06: white_balance
    0x0a: blank_screen
    0x0b: black_border
  blank_screen_detection:
    0x01: low_brightness
    0x02: same_tone
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
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
      - id: reserved
        contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
  video_body:
    seq:
      - id: source
        type: u1
        enum: video_source
      - id: region
        type: u1
        enum: video_region
      - id: saturation
        type: u1
      - id: sound_effects
        type: u1
      - id: sound_type
        contents: [0x02]
      - id: softness
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
        valid: 0
      - id: strip_right_percent
        type: u1
        valid: 0
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
            'display_setting::black_border': black_border_payload
  white_balance_payload:
    seq:
      - id: progress
        type: u1
        valid:
          min: 1
          max: 100
  black_border_payload:
    seq:
      - id: is_on
        type: u1
  blank_screen_payload:
    seq:
      - id: is_on
        type: u1
      - id: detection
        type: u1
        enum: blank_screen_detection
      - id: low_brightness_duration_seconds
        type: u2
      - id: same_tone_duration_seconds
        type: u2
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
