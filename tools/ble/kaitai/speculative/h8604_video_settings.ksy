meta:
  id: h8604_video_settings
  title: Govee H8604 HDMI video registers
  endian: le
doc: |
  SPECULATIVE exact H8604 video-setting writes and queries. Register A9/01
  controls video sensitivity. Register A9/03 selects one of four HDMI inputs
  using the one-based wire values 1 through 4.
  Register A9/05 controls yellow, blue and
  purple calibration; qualified HDR revisions append red calibration.
  Register A9/0e mirrors saturation. The same typed bodies describe status
  replies after an A9 status domain.
seq:
  - id: header
    contents: [0x33, 0xa9]
  - id: body
    size: 17
    type: setting_body
  - id: checksum
    type: u1
types:
  setting_body:
    seq:
      - id: setting
        type: u1
        enum: setting
      - id: length
        type: u1
        valid:
          any-of: [1, 2, 3, 4, 6]
      - id: payload
        size: length
        type:
          switch-on: setting
          cases:
            'setting::sensitivity': scalar_payload
            'setting::hdmi_input': hdmi_input_payload
            'setting::colour_calibration': colour_calibration_payload
            'setting::blank_screen': blank_screen_payload
            'setting::black_border': scalar_payload
            'setting::saturation': scalar_payload
      - id: unknown_tail
        size-eos: true
  scalar_payload:
    seq:
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  hdmi_input_payload:
    seq:
      - id: selected
        type: u1
        valid:
          min: 1
          max: 4
      - id: connected_mask
        type: u1
        if: _parent.length == 2
      - id: unknown_tail
        size-eos: true
  colour_calibration_payload:
    seq:
      - id: yellow
        type: u1
        valid:
          min: 1
          max: 100
      - id: blue
        type: u1
        valid:
          min: 1
          max: 100
      - id: purple
        type: u1
        valid:
          min: 1
          max: 100
      - id: red
        type: u1
        valid:
          min: 1
          max: 100
        if: _parent.length == 4
      - id: unknown_tail
        size-eos: true
  blank_screen_payload:
    seq:
      - id: is_enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: detection
        type: u1
        valid:
          any-of: [1, 2]
      - id: low_brightness_duration_seconds
        type: u2
      - id: same_tone_duration_seconds
        type: u2
  query:
    seq:
      - id: header
        contents: [0xaa, 0xa9]
      - id: setting
        type: u1
        enum: setting
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
enums:
  setting:
    0x01: sensitivity
    0x03: hdmi_input
    0x05: colour_calibration
    0x0a: blank_screen
    0x0b: black_border
    0x0e: saturation
