meta:
  id: h6199_upload_ack_payload
  title: H6199 A3 DIY upload acknowledgement payload
  endian: le
doc: |
  SPECULATIVE H6199 response hypothesis from issue #115 live qualification.
  On 2026-09-17 HW 3.02.01/FW 1.10.04 returned the same checksum-valid
  A3/04/00 response three times during palette DIY workflows. These are
  integration notifications, not official-app captures.
  Android 7.6.01 pact_tvlightv2/iot/OpDiyCommDialog4BleIot selects
  base2light/ble/controller/MultipleDiyControllerV1 (command 4), inheriting
  AbsMultipleControllerV1 (protocol A3, result at absolute byte 2, zero success).
  AbsController matches protocol/command only. The sixteen trailing bytes have
  no established meaning and are preserved. Negative results, nonzero tails,
  other upload commands/revisions and timing remain physically unqualified.
  This result does not identify an effect or establish applied device state.
seq:
  - id: opcode
    type: u1
    valid: 0x04
  - id: status
    type: u1
  - id: unknown_tail
    size: 16
instances:
  is_success:
    value: status == 0
