meta:
  id: h60a6_command_ack
  title: H60A6 ordinary and native effect acknowledgements
  endian: le
doc: |
  SPECULATIVE H60A6 support for issue #402.  Compatibility hypothesis:
  ordinary 33 and A4/58 replies put the result after the opcode, whereas
  A3/58 has one opaque byte before the result.  Zero denotes success.
  Acknowledgements have
  no transaction identifier or content/readback guarantee.  Their timing,
  late duplicates and revision coverage require capture qualification.
  Unknown suffix bytes remain opaque.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3, 0xa4]
  - id: opcode
    type: u1
  - id: unknown_a3_prefix
    type: u1
    if: protocol == 0xa3 and opcode == 0x58
  - id: status
    type: u1
  - id: unknown_tail
    size: 'protocol == 0xa3 and opcode == 0x58 ? 15 : 16'
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == 0xa3 or protocol == 0xa4
  is_success:
    value: status == 0
