meta:
  id: status_query
  title: Govee H617A "aa" status-query envelope
  endian: le
doc: |
  H617A 20-byte status query. The final byte is the XOR of bytes 0 through 18.
  Issue #286 AA0F reuses zero_body based on Android 7.6.01 LightNumController /
  AbsOnlyReadSingleController and direct H617A queries, not official-app captures.
  This route remains speculative; see speculative/h617a_control_payload.ksy.
  AA0501 is also produced by Android 7.6.01
  com/govee/base2light/ble/controller/AbsModeController.p(), inherited by
  dreamcolorlightv1/ble/ModeController on the H6102 goods-18 route (#115).
  Direct H617A queries answered both AA0500 and AA0501 (2026-09-16).
  This does not establish that AA0500 fails on H6102.
  H6102 #115 limit/gradual queries use the shared zero body: Android 7.6.01
  dreamcolorlightv1/ble/LimitController and Gradual4BleWifiController inherit
  AbsSingleController.p. Product authorization remains in the effective profile.
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
        'query_domain::light_count': zero_body
        'query_domain::limit': zero_body
        'query_domain::multi_effect': zero_body
        'query_domain::segments': segment_query_body
        'query_domain::display_setting': display_setting_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x0e: limit
    0x0f: light_count
    0xa3: multi_effect
    0xa5: segments
    0xa9: display_setting
  display_setting:
    0x06: scalar_white_balance
types:
  colour_mode_query_body:
    seq:
      - id: selector
        type: u1
        valid:
          any-of: [0, 1]
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  display_setting_query_body:
    doc: Scalar readback query evidenced in issue 303; model qualification is independent.
    seq:
      - id: setting
        type: u1
        enum: display_setting
        valid: display_setting::scalar_white_balance
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
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
  segment_query_body:
    doc: Selects one of five three-segment reply groups.
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 5
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
