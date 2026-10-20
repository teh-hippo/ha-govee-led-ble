meta:
  id: h617a_command_ack
  title: H617A ordinary and A3 command acknowledgement
  endian: le
doc: |
  SPECULATIVE H617A support work under capability umbrella issue #286.
  Android 7.6.01 base2light/ble/controller/AbsSingleController.t reads ordinary
  result byte 2. MultiDiyTempalteController inherits AbsMultipleControllerV1.q
  (default 2); MultipleController4Music inherits AbsMultipleControllerV2.j
  (result byte 3). Zero means success. Exact H617A UiV3/BleOpV3 use these
  controllers and activate native DIY/music only after a positive upload result.
  Hypothesis: these APK consumers describe H617A replies on the tested revision.
  Ordinary positive replies have direct-device evidence; A3/negative replies,
  suffixes, timing and other revisions lack official-app capture/owner qualification.
  AbsController.isSameController matches protocol and command only. Music byte 2
  is not a transaction ID.  An H6076 capture (issue #343) shows it repeating the
  music mode; the H617A value remains unconfirmed, so the field keeps its name.
  A delayed same-subtype ACK during a later
  final attempt is indistinguishable. ACK never establishes applied device state.
  H617E and other command_grammar=H617A consumers structurally share this parser;
  this adds no exact-SKU ACK qualification or upload-ACK policy for them. H6099
  retains its independent speculative command-ACK parser and upload policy.
  H6102 #115 independently reaches this same encoding via goods-18 Pact 10
  UiV3 -> MultipleDiyControllerV1 / MultiDiyTempalteController (A3/04 and
  A3/02, status at absolute byte 2), and MultipleController4Music (A3/41,
  status at absolute byte 3). Shared no-event consumers corroborate it:
  base2light/ble/controller/AbsControllerNoEvent4Multi.java:36-38,84-102
  matches protocol/opcode and tests byte 2 for zero; its WithSub subclass
  AbsControllerNoEvent4MultiWithSub.java:12-15 overrides the index to 3.
  No byte-2 transaction token is inferred for music. H6102 policy requires
  positive upload ACK before activation; schema reuse is not donor qualification.
  H7020 #363 reuses ordinary zero-success ACKs, including configured strings,
  and the A3/02 and A3/04 result-byte-2 forms. This is candidate structural
  compatibility, not exact-model capture qualification or state confirmation.
  H7025 #148 independently reaches MusicControllerNoEvent3Result through
  H7025MusicMode and MusicModeComposeController (A3/41 result byte 3) and the
  shared A3/02 and A3/04 result-byte-2 controllers for scenes and DIY, with
  protocol/opcode correlation. Its candidate requires a positive result before
  activation. No H7025 mode echo, transaction token or LAN receipt guarantee
  is inferred from the H607C observation in that issue.
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
