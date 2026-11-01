meta:
  id: h607c_status_reply
  title: H607C candidate ordinary and native-setting replies
  endian: le
  imports:
    - h6102_status_reply
    - h607c_control
    - h607c_music_write
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: basic and identity fields share the common
  layouts. Device-info 07/08 carries brightness before native flags;
  asynchronous EE/30 uses the separate h607c_control notification root.
  Static mode replies retain a mode flag and native Kelvin but do not
  establish complete RGB or thirteen-segment state.
  Unknown bytes, native-white authority and revision timing remain unqualified.
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
        'aa_domain::power': h6102_status_reply::power_body
        'aa_domain::brightness': h6102_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': hardware_body
        'aa_domain::power_on_behaviour': h607c_control::power_on_state
        'aa_domain::multi_effect': h607c_control::gradual_state
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x41: power_on_behaviour
    0xa3: multi_effect
  hardware_selector:
    3: version
    8: device_info
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
instances:
  is_device_info:
    value: domain == aa_domain::hw_version and body.as<hardware_body>.selector == hardware_selector::device_info
types:
  hardware_body:
    seq:
      - id: selector
        type: u1
        enum: hardware_selector
      - id: detail
        size-eos: true
        type:
          switch-on: selector
          cases:
            'hardware_selector::version': h6102_status_reply::version_body
            'hardware_selector::device_info': h607c_control::device_info
    instances:
      text:
        value: detail.as<h6102_status_reply::version_body>.text
        if: selector == hardware_selector::version
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
            'color_mode::static': cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': cm_diy
            'color_mode::music': h607c_music_write::music_selector
  cm_static:
    seq:
      - id: unknown_mode_flag
        type: u1
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  cm_diy:
    seq:
      - id: code
        type: u2le
      - id: companion
        type: u2le
      - id: unknown_tail
        size-eos: true
