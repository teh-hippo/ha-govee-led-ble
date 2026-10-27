meta:
  id: h6072_music_ack
  title: H6072 candidate music companion acknowledgement
  endian: le
  imports:
    - h6076_music_body
doc: |
  SPECULATIVE H6072, owner confirmations #486.
  Compatibility hypothesis: A3 subtype 41 has a mode and result, with zero
  indicating upload success. This is separate from active-selection readback.
  Exact-model mode echo, other result values and timing are unqualified.
seq:
  - id: protocol
    contents: [0xa3]
  - id: opcode
    type: u1
    valid: 0x41
  - id: mode
    type: u1
    enum: h6076_music_body::music_mode
  - id: status
    type: u1
  - id: unknown_tail
    size: 15
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: protocol[0]
  is_success:
    value: status == 0
