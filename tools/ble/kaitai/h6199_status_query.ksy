meta:
  id: h6199_status_query
  title: Govee H6199 "aa" status-query envelope (decode-only)
  endian: le
doc: |
  H6199 20-byte status query. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: query_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'query_domain::power': zero_body
        'query_domain::brightness': zero_body
        'query_domain::colour_mode': zero_body
        'query_domain::firmware': zero_body
        'query_domain::hardware': hardware_query_body
        'query_domain::identity': zero_body
        'query_domain::subordinate_20': zero_body
        'query_domain::subordinate_21': zero_body
        'query_domain::display_setting': display_setting_query_body
        'query_domain::relative_brightness': relative_brightness_query_body
        'query_domain::segments': segment_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x14: identity
    0x20: subordinate_20
    0x21: subordinate_21
    0xa9: display_setting
    0xae: relative_brightness
    0xa5: segments
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
types:
  zero_body:
    seq:
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  hardware_query_body:
    seq:
      - id: selector
        contents: [0x03]
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  display_setting_query_body:
    seq:
      - id: setting
        type: u1
        enum: display_setting
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  relative_brightness_query_body:
    seq:
      - id: selector
        contents: [0x01]
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  segment_query_body:
    doc: Selects groups 1 through 3 with four segment records, or group 4 with three.
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 4
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
