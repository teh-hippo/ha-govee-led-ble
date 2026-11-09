meta:
  id: h1771_music_ack
  title: H1771 candidate multipart upload acknowledgement
  endian: le
doc: |
  SPECULATIVE: H1771 music and native DIY upload acknowledgements reconstructed from
  behaviour, not confirmed by device traffic.  The status byte is zero on
  success.  The preceding byte and remaining suffix are not qualified as a
  mode echo and remain opaque.
seq:
  - id: protocol
    contents: [0xa3]
  - id: opcode
    type: u1
    enum: command
  - id: unknown
    type: u1
  - id: status
    type: u1
  - id: unknown_tail
    size: 15
  - id: checksum
    type: u1
enums:
  command:
    0x41: music_upload
    0x58: native_diy_upload
instances:
  protocol_id:
    value: protocol[0]
  is_upload:
    value: opcode == command::music_upload or opcode == command::native_diy_upload
  is_success:
    value: status == 0
