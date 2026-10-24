meta:
  id: h6099_status_query
  title: Govee H6099 logical status query
  endian: le
doc: |
  SPECULATIVE H6099 query frame for issue #258.  In Android 7.6.01, H6099 mode
  queries use selector 01 and segment queries request four groups for fourteen
  logical zones.  Scalar white balance uses A9 06, black-border removal uses
  A9 0B, and relative brightness uses AE 01.  AA40 queries the signed
  big-endian physical IC count (distinct from the 14 logical zones).  AA20 and
  AA21 query Wi-Fi hardware and software identity.  AA30 queries installation
  direction and AA32 queries camera health with zero-filled bodies; camera
  position (31) is separate and not queried here.  Encryption is outside this
  logical frame; owner acceptance, firmware differences, and unused bytes
  remain unresolved.
  H6097 issue #431 independently shares these query selectors and fourteen-zone
  paging.  Its ordinary three-state power-on query has a separate exact root.
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
        'query_domain::colour_mode': colour_mode_query_body
        'query_domain::firmware': zero_body
        'query_domain::hardware': hardware_query_body
        'query_domain::physical_ic_count': zero_body
        'query_domain::subordinate_20': zero_body
        'query_domain::subordinate_21': zero_body
        'query_domain::display_setting': display_setting_query_body
        'query_domain::relative_brightness': relative_brightness_query_body
        'query_domain::segments': segment_query_body
        'query_domain::installation_direction': zero_body
        'query_domain::camera_health': zero_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x40: physical_ic_count
    0x20: subordinate_20
    0x21: subordinate_21
    0x30: installation_direction
    0x32: camera_health
    0xa9: display_setting
    0xae: relative_brightness
    0xa5: segments
  display_setting:
    0x06: scalar_white_balance
    0x0a: blank_screen
    0x0b: black_border
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
  colour_mode_query_body:
    seq:
      - id: selector
        contents: [0x01]
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
