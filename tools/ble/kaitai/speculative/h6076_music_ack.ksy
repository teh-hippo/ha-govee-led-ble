meta:
  id: h6076_music_ack
  title: Govee H6076 speculative music companion acknowledgement
  endian: le
  imports:
    - h6076_music_body
doc: |
  H6076.
  Evidence source classes: a reporter's report on an H6076 (hardware 3.05.00,
  software 1.04.05, V1 encrypted session) of an A3 reply of this shape after each
  companion upload, and the observation that status at byte 3 is zero on success.
  Replies match on protocol and command only, so the mode echo at byte 2 is
  single-source evidence.
  Compatibility hypothesis: the lamp answers each A3 command 0x41 upload with a
  20-byte reply that repeats the uploaded mode and carries a zero status on
  success.  The reply does not establish applied device state.
  Unresolved assumptions: status values other than zero, the unused bytes, whether
  other hardware revisions repeat the mode, and the reply timing.  The final byte
  is the XOR of bytes 0 through 18.
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
