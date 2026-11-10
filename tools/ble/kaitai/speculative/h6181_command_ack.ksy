meta:
  id: h6181_command_ack
  title: Govee H6181 command and upload acknowledgements
  endian: be
doc: |
  SPECULATIVE H6181 candidate acknowledgements. Ordinary commands and A1/02
  or A3/01/04 uploads report zero-success at byte 2. A3/41 music places the
  status at byte 3. Prefixes and suffixes are not transaction identifiers.
  An acknowledgement is not confirmation of the rendered state.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa1, 0xa3]
  - id: opcode
    type: u1
  - id: unknown_music_prefix
    type: u1
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
    value: protocol == 0xa1 or protocol == 0xa3
  is_success:
    value: status == 0
