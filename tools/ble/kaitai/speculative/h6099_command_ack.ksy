meta:
  id: h6099_command_ack
  title: Govee H6099 logical command acknowledgement
  endian: le
doc: |
  SPECULATIVE H6099 command ACK for issue #258. Android 7.6.01
  pact_h6099 controllers inherit AbsControllerNoEvent4Single, whose onResult
  reads a success byte at body offset zero. Tail bytes remain unknown; this
  structure records receipt, never setting values or fresh device state.
  Exact-device reply tails, firmware differences and encryption need owner
  qualification. Only in-scope command opcodes are named.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
    valid:
      any-of: [command_op::power, command_op::brightness, command_op::mode, command_op::installation_direction, command_op::display_setting, command_op::relative_brightness]
  - id: status
    type: u1
    valid: 0
  - id: unknown_tail
    size: 16
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0x30: installation_direction
    0xa9: display_setting
    0xae: relative_brightness
