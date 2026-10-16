meta:
  id: h6199_pact1_wire_write
  title: Govee H6199 Pact 1 legacy brightness and static RGB wire writes
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6199 Pact 1/1, issue #293.
  Compatibility hypothesis: the legacy producer uses a scaled 20..254 brightness
  register and static-colour selector 0x0b with RGB, a two-byte Kelvin field and
  a little-endian fifteen-bit segment mask.  Runtime authoring permits only
  whole-strip RGB with zero Kelvin; the shared H6199 logical commands retain
  capability checks and optimistic semantics before this wire transform.
  Unresolved assumptions: independent official-app captures at known brightness
  percentages, device qualification of both writes, unused frame bytes and
  command echoes.  This root does not qualify readback or other legacy modes.
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
        'command_op::mode': mode_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x04: brightness
    0x05: mode
  mode_sel:
    0x0b: static_colour
types:
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: unknown_tail
        size-eos: true
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::static_colour': static_colour_body
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: segment_mask
        type: u2
      - id: unknown_tail
        size-eos: true
