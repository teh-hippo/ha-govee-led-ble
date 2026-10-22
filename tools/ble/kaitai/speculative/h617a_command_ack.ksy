meta:
  id: h617a_command_ack
  title: H617A ordinary and A3 command acknowledgement
  endian: le
doc: |
  SPECULATIVE H617A support work under capability umbrella issue #286.
  In Android 7.6.01, ordinary 0x33 command replies and A3/02 or A3/04 DIY/scene
  uploads report status at absolute byte 2, whereas A3/41 music uploads report
  status at absolute byte 3, with zero meaning success.  The H617A workflow
  activates native DIY and music only after a positive upload result.
  Hypothesis: these acknowledgement layouts describe H617A replies on the tested
  revision.  Ordinary positive replies have direct-device evidence; A3/negative
  replies, suffixes, timing, and other revisions lack official-app capture or
  owner qualification.  Replies match protocol and command only.  Music byte 2
  is not a transaction ID.  An H6076 capture (issue #343) shows it repeating the
  music mode; the H617A value remains unconfirmed, so the field keeps its name.
  A delayed same-subtype ACK during a later final attempt is indistinguishable.
  ACK never establishes applied device state.
  H617E and other command_grammar=H617A consumers structurally share this parser;
  this adds no exact-SKU ACK qualification or upload-ACK policy for them.  H6099
  retains its independent speculative command-ACK parser and upload policy.
  H6102 #115 (goods type 18, Pact 10) and H7025 #148 independently use the same
  A3/02 and A3/04 byte-2 and A3/41 byte-3 acknowledgement layouts and require a
  positive upload result before activation; schema reuse is not donor
  qualification, and no H7025 mode echo, transaction token, or LAN receipt
  guarantee is inferred from the H607C observation in #148.
  H7020 #363 reuses ordinary zero-success ACKs, including configured strings,
  and the A3/02 and A3/04 result-byte-2 forms.  This is candidate structural
  compatibility, not exact-model capture qualification or state confirmation.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3]
  - id: opcode
    type: u1
  - id: unknown_music_prefix
    type: u1
    if: is_upload and opcode == 0x41
  - id: status
    type: u1
  - id: unknown_tail
    size: 'is_upload and opcode == 0x41 ? 15 : 16'
  - id: checksum
    type: u1
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == 0xa3
  is_success:
    value: status == 0
