meta:
  id: h6053_command_ack
  title: Govee H6053 ordinary and multipart upload acknowledgements
  endian: le
  imports:
    - h6046_command_write
doc: |
  SPECULATIVE H6053 ordinary and multipart upload results across both Pacts.
  Ordinary 33 replies, A1 command-02 replies and A3 RGB/V1/DIY/V2 replies
  carry their result at offset 2. A3 music replies echo the mode at offset 2
  and carry the result at offset 3. Zero accepts the upload, not its later
  activation or visible rendering. Correlate protocol, subtype and music
  mode. Reply timing, nonzero results and suffix bytes remain unqualified.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa1, 0xa3]
  - id: opcode
    type: u1
  - id: mode
    type: u1
    enum: h6046_command_write::music_mode
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
    value: (protocol == 0xa1 and opcode == 0x02) or (protocol == 0xa3 and (opcode == 0x01 or opcode == 0x02 or opcode == 0x04 or opcode == 0x0a or opcode == 0x41))
  is_success:
    value: status == 0
