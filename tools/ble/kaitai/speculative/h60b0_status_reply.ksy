meta:
  id: h60b0_status_reply
  title: H60B0 candidate ordinary and source status
  endian: le
  imports:
    - ../govee_segment_page
    - h6102_status_reply
    - h60b0_command_write
doc: |
  SPECULATIVE: Exact-model reply layouts remain partly unconfirmed.
  Source flags occupy the high nibble, independently of lower unknown bits.
  Source state carries top Kelvin/ripple speed before bottom Kelvin/brightness,
  as corroborated by recorded AA42 and AA05 replies. A5 records cover eight
  side colours and the top colour only.
  The candidate EF identity reply carries Pact type BE16 and Pact code.
  Captured EE30 source notifications carry an opaque prefix then the same
  high-nibble power flags; their suffix does not confirm native attributes.
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
        'status_domain::power': h6102_status_reply::power_body
        'status_domain::brightness': percent_body
        'status_domain::colour_mode': mode_body
        'status_domain::fw_version': h6102_status_reply::version_body
        'status_domain::hw_version': h6102_status_reply::hw_version_body
        'status_domain::source_info': source_info
        'status_domain::power_on_behaviour': power_on_body
        'status_domain::segments': govee_segment_page(9, 4, false)
        'status_domain::pact': pact_body
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: fw_version
    0x07: hw_version
    0x41: power_on_behaviour
    0x42: source_info
    0xa5: segments
    0xef: pact
  color_mode:
    0x04: scene
    0x0a: diy
    0x0d: static
    0x13: music
    0x2c: source_control
types:
  pact_body:
    seq:
      - id: pact_type
        type: u2be
      - id: pact_code
        type: u1
      - id: unknown_tail
        size-eos: true
  source_notification:
    seq:
      - id: header
        contents: [0xee, 0x30]
      - id: unknown_prefix
        type: u1
      - id: flags
        type: u1
      - id: unknown_tail
        size: 15
      - id: checksum
        type: u1
    instances:
      is_on:
        value: (flags & 0x80) != 0
      top_enabled:
        value: (flags & 0x40) != 0
      side_enabled:
        value: (flags & 0x20) != 0
      bottom_enabled:
        value: (flags & 0x10) != 0
  percent_body:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  operation_state:
    seq:
      - id: top_kelvin
        type: u2be
      - id: ripple_speed
        type: u1
      - id: bottom_kelvin
        type: u2be
      - id: bottom_brightness
        type: u1
      - id: unknown_tail
        size-eos: true
  source_info:
    seq:
      - id: flags
        type: u1
      - id: operation
        type: operation_state
    instances:
      master_enabled:
        value: (flags & 0x80) != 0
      top_enabled:
        value: (flags & 0x40) != 0
      side_enabled:
        value: (flags & 0x20) != 0
      bottom_enabled:
        value: (flags & 0x10) != 0
  power_on_body:
    seq:
      - id: selector
        type: u1
      - id: state
        type: u1
        enum: h60b0_command_write::power_on_state
      - id: unknown_tail
        size-eos: true
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::static': h60b0_command_write::whole_colour
            'color_mode::music': h60b0_command_write::music_selector
            'color_mode::source_control': operation_state
