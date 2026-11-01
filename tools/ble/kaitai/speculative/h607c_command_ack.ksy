meta:
  id: h607c_command_ack
  title: H607C candidate ordinary and multipart results
  endian: le
  imports:
    - h607c_music_write
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: ordinary multipart results carry zero-success
  immediately after the command. Music 41 repeats its mode before the result.
  A result confirms acceptance only, not rendering or uploaded-content readback.
  Physical emission, timing and late duplicate behaviour remain unqualified.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3]
  - id: opcode
    type: u1
  - id: mode
    type: u1
    enum: h607c_music_write::music_mode
    if: protocol == 0xa3 and opcode == 0x41
  - id: status
    type: u1
  - id: unknown_tail
    size: 'protocol == 0xa3 and opcode == 0x41 ? 15 : 16'
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == 0xa3
  is_success:
    value: status == 0
