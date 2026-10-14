meta:
  id: h6102_wire_write
  title: Govee H6102 Pact 1 brightness register write
  endian: le
doc: |
  SPECULATIVE H6102, issues #115 and #310.
  Evidence source class: reachable Android 7.6.01 producer/consumer behaviour
  and the #310 owner's AA04 reply. No official-app BLE capture is available.
  Compatibility hypothesis: Pact 1 codes 1 and 2 use a 20..254 master
  brightness register, independently of the static RGB generation.
  The shared logical command remains a percentage; the exact-model profile
  transforms it into this register write. Pact 10 continues to use percentages.
  Unresolved assumptions: physical brightness calibration, reply freshness,
  write echo behaviour and unused bytes across firmware revisions.
  The final byte is the XOR of bytes 0 through 18.
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
        'command_op::brightness': brightness_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x04: brightness
types:
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: padding
        size-eos: true
