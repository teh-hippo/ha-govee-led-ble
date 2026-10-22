meta:
  id: h6076_music_ack
  title: Govee H6076 speculative music companion acknowledgement
  endian: le
  imports:
    - h6076_music_body
doc: |
  SPECULATIVE H6076, issue #343.
  Evidence source classes: a reporter's decrypted Android HCI snoop of the Govee
  app driving an H6076 (hardware 3.05.00, software 1.04.05, V1 encrypted
  session), which lists an A3 reply of this shape after each companion upload,
  and Android Govee 7.5.30 upload acknowledgement handling, which reads the
  status at byte 3 and treats zero as success.  The app matches replies on
  protocol and command only, so the mode echo at byte 2 is capture-only evidence.
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
