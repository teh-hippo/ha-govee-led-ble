meta:
  id: h6099_command_ack
  title: Govee H6099 logical command and effect-upload acknowledgement
  endian: le
doc: |
  H6099 single-frame command handlers read a zero success byte at body offset
  zero. A3 scene and DIY replies place the upload result at absolute byte 2;
  music replies place it at byte 3 and preserve an unknown value at byte 2.
  Tail bytes remain unknown. These replies record upload completion, never
  fresh applied-device state. Exact-device reply tails, firmware differences,
  encryption and timing need owner qualification. Only in-scope command
  opcodes are named.
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
      any-of: [command_op::power, command_op::brightness, command_op::mode, command_op::installation_direction, command_op::display_setting, command_op::relative_brightness]
  - id: status
    type: u1
    if: header == 0x33
    valid: 0
  - id: unknown_tail
    size: 16
    if: header == 0x33
  - id: upload
    type: upload_ack
    if: header == 0xa3
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: header
  is_upload:
    value: header == 0xa3
  is_success:
    value: 'header == 0x33 ? status == 0 : upload.is_success'
types:
  upload_ack:
    seq:
      - id: opcode
        type: u1
      - id: unknown_music_prefix
        type: u1
        if: opcode == 0x41
      - id: status
        type: u1
      - id: unknown_tail
        size: 'opcode == 0x41 ? 15 : 16'
    instances:
      is_success:
        value: status == 0
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0x30: installation_direction
    0xa9: display_setting
    0xae: relative_brightness
