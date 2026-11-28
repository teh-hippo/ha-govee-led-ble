meta:
  id: h60b0_command_ack
  title: H60B0 candidate ordinary and upload acknowledgements
doc: |
  SPECULATIVE: Exact-model controller contracts, not recorded device replies.
  Ordinary commands and uploads carry the result at offset 2. Music echoes
  its selector at offset 2 and reports the result at offset 3. Both 5a and
  0a scene upload acknowledgements remain schema candidates; zero means
  acceptance only, not visible rendering confirmation.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3]
  - id: opcode
    type: u1
  - id: mode
    type: u1
    if: protocol == 0xa3 and opcode == upload_kind::music.to_i
  - id: status
    type: u1
  - id: unknown_tail
    size: 'protocol == 0xa3 and opcode == upload_kind::music.to_i ? 15 : 16'
  - id: checksum
    type: u1
enums:
  upload_kind:
    0x0a: rgbic_scene
    0x41: music
    0x58: native_diy
    0x5a: combined_scene
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == 0xa3 and (opcode == upload_kind::rgbic_scene.to_i or opcode == upload_kind::music.to_i or opcode == upload_kind::native_diy.to_i or opcode == upload_kind::combined_scene.to_i)
  is_success:
    value: status == 0
