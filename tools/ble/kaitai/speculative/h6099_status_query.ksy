meta:
  id: h6099_status_query
  title: Govee H6099 logical status query
  endian: le
doc: |
  SPECULATIVE H6099 query frame for issue #258, ported from the issue branch.
  Android 7.6.01 pact_h6099 active-detail ControllerMode uses selector 01;
  colour pages use four groups for fourteen logical zones. Scalar white balance
  uses A9 06 and relative brightness AE 01. Encryption is outside this logical
  frame. Owner acceptance, firmware differences and unused bytes are unresolved.
  ControllerIcNum.readController uses AA40 with no payload; the corresponding
  physical count is signed big-endian in NewDetailVm$connectBleSuc$1, not 14 zones.
  PairAcV1 uses WifiHardVersionController (20) and WifiSoftVersionController (21).
  detail/NewDetailVm uses BlackBorderRemoveController to query A9 0B.
  pact_h6099/ble/controller/compose/DirectionController queries AA30;
  HasCameraController queries AA32. Both have no payload. Camera position
  (CameraPosController, 31) is separate and not queried here.
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
