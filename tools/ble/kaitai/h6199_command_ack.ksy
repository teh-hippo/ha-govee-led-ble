meta:
  id: h6199_command_ack
  title: Govee H6199 generic command acknowledgement
  endian: le
doc: |
  H6199 display-setting and relative-brightness writes acknowledge with the command opcode,
  a zero success byte, and zero padding. The acknowledgement does not echo the setting or
  value, so callers verify changes with the corresponding status query.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
    valid:
      any-of:
        - command_op::power
        - command_op::mode
        - command_op::display_setting
        - command_op::relative_brightness
  - id: status
    type: u1
    valid: 0
  - id: padding
    contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x05: mode
    0xa9: display_setting
    0xae: relative_brightness
