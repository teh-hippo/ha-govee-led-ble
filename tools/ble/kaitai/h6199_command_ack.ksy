meta:
  id: h6199_command_ack
  title: Govee H6199 generic command acknowledgement
  endian: le
  imports:
    - speculative/h6199_upload_ack_payload
doc: |
  H6199 display-setting and relative-brightness writes acknowledge with the command opcode,
  a zero success byte, and zero padding. The acknowledgement does not echo the setting or
  value, so callers verify changes with the corresponding status query.
  Issue #294 direction30, position31 and Gradient A3 ACKs were observed in
  direct-register tests, not official-app BLE captures. Their use remains
  speculative; a zero ACK never establishes changed state.
  A3/04 DIY upload responses observed during issue #115 live qualification use
  the separate speculative payload; they are acknowledgements, not status.
seq:
  - id: header
    type: u1
    valid:
      any-of: [0x33, 0xa3]
  - id: opcode
    type: u1
    if: header == 0x33
    enum: command_op
    valid:
      any-of:
        - command_op::power
        - command_op::mode
        - command_op::display_setting
        - command_op::relative_brightness
        - command_op::strip_direction
        - command_op::camera_position
        - command_op::gradient
  - id: status
    type: u1
    valid: 0
    if: header == 0x33
  - id: padding
    contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    if: header == 0x33
  - id: upload
    type: h6199_upload_ack_payload
    if: header == 0xa3
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x05: mode
    0x30: strip_direction
    0x31: camera_position
    0xa3: gradient
    0xa9: display_setting
    0xae: relative_brightness
