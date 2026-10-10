meta:
  id: h601c_command_write
  title: Govee H601C command-write envelope
  endian: le
  imports:
    - ../govee_shared
    - ../govee_common
doc: |
  SPECULATIVE H601C support work.
  Hypothesis: Govee H601C recessed downlight uses standard 20-byte 0x33 command
  framing with zero-padding and XOR checksum at byte 19. Supports basic power (0x01),
  brightness (0x04), and manual single-light colour / tunable white (CCT) modes
  via opcode 0x05 with sub-opcode 0x0D (decimal 13):
  - Manual RGB: 33 05 0d <R> <G> <B> 00 00 ... [xor]
  - Tunable white: 33 05 0d ff ff ff <k_hi> <k_lo> ... [xor]
  Physically verified on H601C hardware with live ACK (33 05 00) and register
  confirmation (aa 05 0d ...).
  Unresolved assumptions: multi-fixture BLE group synchronization, scene
  activation payloads, and music modes remain unverified and are intentionally
  excluded from the runtime profile.
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
        'command_op::power': power_cmd
        'command_op::brightness': brightness_cmd
        'command_op::colour': colour_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: colour
  colour_mode:
    0x0d: colour_or_cct
types:
  power_cmd:
    seq:
      - id: is_on
        type: u1
  brightness_cmd:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
  colour_cmd:
    seq:
      - id: mode
        type: u1
        enum: colour_mode
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'colour_mode::colour_or_cct': manual_colour_or_cct
  manual_colour_or_cct:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
        doc: 0 for manual RGB mode, or Kelvin (2700..6500) for tunable white mode with rgb=0xFFFFFF
