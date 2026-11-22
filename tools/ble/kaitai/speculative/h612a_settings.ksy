meta:
  id: h612a_settings
  title: Govee H612A power-on and strip-calibration commands
  endian: le
doc: |
  SPECULATIVE: H612A power-on behaviour and IC endpoint calibration.
  Power-on writes select state with a leading 0x02 field.  Calibration writes
  combine a workflow action, source channel and big-endian IC position.
  The first and final calibration actions use position zero.  No complete owner
  capture is available yet; unknown fields remain opaque.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command
    valid:
      any-of: [command::power_on_behaviour, command::strip_calibration]
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command::power_on_behaviour': power_on_command
        'command::strip_calibration': calibration_command
  - id: checksum
    type: u1
enums:
  command:
    0x41: power_on_behaviour
    0x46: strip_calibration
  power_on_state:
    0: previous
    1: "on"
    2: "off"
  calibration_operation:
    0: start
    1: locate
    2: cancel
    4: confirm
types:
  power_on_command:
    seq:
      - id: selector
        type: u1
        valid: 2
      - id: state
        type: u1
        enum: power_on_state
      - id: unknown_tail
        size-eos: true
  calibration_command:
    seq:
      - id: operation
        type: u1
        enum: calibration_operation
      - id: source
        type: u1
        valid: 0
      - id: ic_count
        type: u2be
      - id: unknown_tail
        size-eos: true
  power_on_query:
    seq:
      - id: header
        contents: [0xaa, 0x41, 0x00]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
