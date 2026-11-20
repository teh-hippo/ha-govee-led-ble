meta:
  id: h1ab2_settings
  title: Govee H1AB2 power-on policy and strip calibration
  endian: be
  imports:
    - h6097_control
doc: |
  SPECULATIVE: Three-state power-on policy writes 41/02 and reads AA41
  without a query selector. Replies carry availability and previous/on/off.
  Length restoration writes 5A/06 with a counted list of big-endian IC counts.
  Cut calibration writes 5A/05, starts endpoint selection with 00, locates
  the last IC with 01/source/IC, then confirms with 04 or cancels with 03.
  H1AB2 has one strip, ten ICs per metre and one-to-five metre choices.
  Ordinary write replies use the shared zero-success acknowledgement.
  Independent AA40 is required to qualify installed geometry afterwards.
  Reply timing and physical calibration remain unconfirmed on hardware.
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
        'command::power_on_behaviour': h6097_control::power_on_command
        'command::strip_calibration': calibration
  - id: checksum
    type: u1
enums:
  command:
    0x41: power_on_behaviour
    0x5a: strip_calibration
  calibration_operation:
    0: start
    1: locate
    3: cancel
    4: confirm
    5: cut
    6: restore
types:
  power_on_query:
    seq:
      - id: header
        contents: [0xaa, 0x41, 0x00]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
  calibration:
    seq:
      - id: operation
        type: u1
        enum: calibration_operation
      - id: detail
        type:
          switch-on: operation
          cases:
            'calibration_operation::locate': location
            'calibration_operation::cut': length
            'calibration_operation::restore': length
      - id: unknown_tail
        size-eos: true
  location:
    seq:
      - id: source
        type: u1
      - id: ic_count
        type: u2
  length:
    seq:
      - id: count
        type: u1
      - id: ic_counts
        type: u2
        repeat: expr
        repeat-expr: count
