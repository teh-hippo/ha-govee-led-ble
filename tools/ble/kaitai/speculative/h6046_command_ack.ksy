meta:
  id: h6046_command_ack
  title: Govee H6046 ordinary and upload acknowledgements
  endian: le
  imports:
    - h6046_command_write
doc: |
  H6046.
  Evidence class: exact-model behavioural audit, not captures or hardware
  qualification. Known Pact 1/1 and 2/1 use ordinary 0x33 command results and
  A3 upload results. Each 20-byte frame ends with XOR of bytes 0..18.
  Ordinary commands echo the opcode and carry a result at offset 2.
  A3 scene 0x02 and DIY 0x04 results also occupy offset 2; music 0x41 instead
  echoes its mode there and places the result at offset 3.
  Zero means upload acceptance, not selector activation or visible rendering.
  Correlate protocol, subtype and music mode, never the mode byte as a result.
  Unresolved assumptions: nonzero result meanings, opaque suffixes, reply
  timing and unreported revisions. No zero-only result or suffix validation.
seq:
  - id: protocol
    type: u1
    valid:
      any-of: [0x33, 0xa3]
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
    value: protocol == 0xa3 and (opcode == 0x02 or opcode == 0x04 or opcode == 0x41)
  is_success:
    value: status == 0
