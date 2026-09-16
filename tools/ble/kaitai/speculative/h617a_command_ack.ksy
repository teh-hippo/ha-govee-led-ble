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
  remains unknown, not a transaction ID. A delayed same-subtype ACK during a later
  final attempt is indistinguishable. ACK never establishes applied device state.
  H617E and other command_grammar=H617A consumers structurally share this parser;
  this adds no exact-SKU ACK qualification or upload-ACK policy for them. H6099
  retains its independent speculative command-ACK parser and upload policy.
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
  is_upload:
    value: protocol == 0xa3
  is_success:
    value: status == 0
