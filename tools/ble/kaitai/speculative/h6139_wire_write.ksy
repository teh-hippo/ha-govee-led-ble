meta:
  id: h6139_wire_write
  title: Govee H6139 whole-strip command frame
  endian: be
  imports:
    - h6181_command_write
    - h6159_wire_write
doc: |
  SPECULATIVE H6139 contract, awaiting recorded device traffic.
  Original controllers use brightness register 6..254 and mode02 RGB,
  temperature flag and companion RGB. Pact10 controllers use percentage
  brightness and mode0D RGB, Kelvin BE16 and companion RGB.
  Original music uses03 before firmware1.03.00, then0E; palettes48/49
  arrive from1.07.00. Later controllers use13, with palette support
  independently qualified by hardware family and firmware2.04.00.
  These independently matched shapes share existing codecs.
  Scenes and DIY use LE16 selectors; original DIY uses A1/02 and later
  DIY uses A3/04. Scene/programme uploads use A3/01 and music A3/41.
  A positive upload verdict precedes activation. Unknown bytes stay opaque.
  Decode-only schedules use timer0A, sleep11 and wake12. Timer records
  place opening and closing times before the slot and repeat byte.
  Repeat bytes and state values are retained without inferred flag semantics.
  These shapes do not authorise runtime scheduling.
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
        'command_op::power': h6181_command_write::power_body
        'command_op::brightness': h6159_wire_write::brightness_body
        'command_op::mode': h6159_wire_write::mode_body
        'command_op::timer': timer_body
        'command_op::sleep': sleep_body
        'command_op::wake': wake_body
  - id: checksum
    type: u1
types:
  timer_body:
    seq:
      - id: state
        type: u1
      - id: open_hour
        type: u1
      - id: open_minute
        type: u1
      - id: close_hour
        type: u1
      - id: close_minute
        type: u1
      - id: slot
        type: u1
      - id: repeat_mask
        type: u1
      - id: opaque
        size-eos: true
  sleep_body:
    seq:
      - id: state
        type: u1
      - id: start_brightness
        type: u1
      - id: duration_minutes
        type: u1
      - id: remaining_minutes
        type: u1
      - id: opaque
        size-eos: true
  wake_body:
    seq:
      - id: state
        type: u1
      - id: target_brightness
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: repeat_mask
        type: u1
      - id: duration_minutes
        type: u1
      - id: opaque
        size-eos: true
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0x0a: timer
    0x11: sleep
    0x12: wake
