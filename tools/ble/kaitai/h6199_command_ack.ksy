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
  direction30, position31 and Gradient A3 ACKs were observed in
  direct-register tests, which are not device-verified. Their use remains
  speculative; a zero ACK never establishes changed state.
  A3/04 and Pact 1 A1/02 DIY upload responses are acknowledgements, not
  status; a zero result succeeds and a nonzero result rejects the upload.
  The A3 response uses the separate speculative payload.
seq:
  - id: header
    type: u1
    valid:
      any-of: [0x33, 0xa1, 0xa3]
  - id: opcode
    type: u1
    if: header == 0x33 or header == 0xa1
    enum: command_op
    valid:
      any-of:
        - command_op::diy_upload
        - command_op::power
        - command_op::mode
        - command_op::display_setting
        - command_op::relative_brightness
        - command_op::strip_direction
        - command_op::camera_position
        - command_op::gradient
  - id: status
    type: u1
    if: header == 0x33 or header == 0xa1
  - id: padding
    contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    if: header == 0x33 or header == 0xa1
  - id: upload
    type: h6199_upload_ack_payload
    if: header == 0xa3
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: header
  is_upload:
    value: 'header == 0xa1 or header == 0xa3'
  is_success:
    value: 'header == 0xa3 ? upload.is_success : status == 0'
enums:
  command_op:
    0x02: diy_upload
    0x01: power
    0x05: mode
    0x30: strip_direction
    0x31: camera_position
    0xa3: gradient
    0xa9: display_setting
    0xae: relative_brightness
