meta:
  id: h600a_command_ack
  title: Govee H600A ordinary and A3 upload acknowledgement
  endian: le
doc: |
  SPECULATIVE H600A support request #492, owner confirmations #494.
  Compatibility hypothesis: ordinary 33 replies and A3/01 scene or A3/04 DIY
  upload results carry a zero-success status at byte 2. Positive upload
  results precede activation; they do not establish state or rendering.
  Unknown suffix bytes remain opaque. Physical reply availability, latency,
  revision differences and correlation beyond protocol/opcode are unqualified.
  No transaction token or safe replay guarantee is inferred.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3]
  - id: opcode
    type: u1
  - id: status
    type: u1
  - id: unknown_tail
    size: 16
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == 0xa3
  is_success:
    value: status == 0
