meta:
  id: h6102_command_write
  title: Govee H6102 "33" command-write envelope
  endian: le
  imports:
    - ../govee_shared
    - h6102_common
doc: |
  SPECULATIVE H6102 schema for #115.
  Evidence source class: public exact-model packet tables and independent
  working implementations; no attributable official-app capture.
  Compatibility hypothesis: H6102 command writes use a 20-byte 0x33 frame with
  observed 0x01 power, 0x04 brightness, and 0x05/0x15/0x01 extended RGB
  layouts; the final byte is the XOR of bytes 0 through 18.
  Unresolved assumptions: power polarity and accepted values, brightness
  boundaries, mask validity and physical mapping, firmware applicability, and
  the meaning of the observed fixed-zero spans are not captured.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': extended_rgb_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
types:
  power_body:
    seq:
      - id: value
        type: u1
      - size: 16
  brightness_body:
    seq:
      - id: percent
        type: u1
      - size: 16
  extended_rgb_body:
    seq:
      - id: selector
        contents: [0x15]
      - id: operation
        contents: [0x01]
      - id: rgb_direct
        type: govee_shared::rgb
      - size: 5
      - id: mask
        type: h6102_common::region_mask_15
      - size: 5
