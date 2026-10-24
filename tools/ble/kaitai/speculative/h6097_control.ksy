meta:
  id: h6097_control
  title: Govee H6097 ordinary three-state power-on setting
  endian: le
  imports:
    - h60a_bulk
doc: |
  SPECULATIVE H6097 support for issue #431.  The ordinary 41 register uses
  selector 02 and the shared previous/on/off state codebook, not a boolean or
  bulk query.  Reply availability/status is independent of the state byte.
  Unknown state values and suffixes remain opaque to runtime semantics.
  Exact-device option mapping, reply timing and other revisions need
  qualification.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command
    valid: command::power_on_behaviour
  - id: body
    size: 17
    type: power_on_command
  - id: checksum
    type: u1
enums:
  command:
    0x41: power_on_behaviour
types:
  power_on_command:
    seq:
      - id: selector
        contents: [0x02]
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
  query:
    seq:
      - id: header
        contents: [0xaa, 0x41, 0x02]
      - id: unknown_tail
        size: 16
      - id: checksum
        type: u1
  power_on_state:
    seq:
      - id: availability
        type: u1
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
      - id: unknown_tail
        size-eos: true
