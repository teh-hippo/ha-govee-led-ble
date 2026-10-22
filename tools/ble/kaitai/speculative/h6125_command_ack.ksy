meta:
  id: h6125_command_ack
  title: Govee H6125 ordinary, A1 and A3 acknowledgements
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: ordinary replies and A1 uploads use result byte 2;
  A3 music uploads use result byte 3, while A3 DIY uses byte 2.
  The shared single-frame, A1, and A3 acknowledgement handlers
  treat zero as success.  Unknown suffixes and music prefixes remain opaque.
  No transaction identifier is inferred.  A same-protocol, same-command delayed
  acknowledgement remains indistinguishable from a later attempt.
  ACK establishes transport acceptance only, not activation or rendering.
seq:
  - id: protocol
    type: u1
    enum: protocol_kind
    valid:
      any-of: [protocol_kind::command, protocol_kind::legacy_upload, protocol_kind::upload]
  - id: opcode
    type: u1
  - id: unknown_music_prefix
    type: u1
    if: protocol == protocol_kind::upload and opcode == 0x41
  - id: status
    type: u1
  - id: unknown_tail
    size: 'protocol == protocol_kind::upload and opcode == 0x41 ? 15 : 16'
  - id: checksum
    type: u1
enums:
  protocol_kind:
    0x33: command
    0xa1: legacy_upload
    0xa3: upload
instances:
  protocol_id:
    value: protocol
  is_upload:
    value: protocol == protocol_kind::legacy_upload or protocol == protocol_kind::upload
  is_success:
    value: status == 0
