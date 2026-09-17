meta:
  id: govee_encryption
  endian: be
doc: |
  SPECULATIVE H6099 encrypted transport, support issue #257 evidence worktree.
  Hypothesis: H6099 uses the shared Govee Home 7.6.01 Android encryption
  controllers (com.govee.encryp.ble). No H6099 official-app capture or owner
  qualification establishes compatibility. V1 uses Controller4Aes/Safe;
  V2 uses Controller4AesGcm with 16-byte tags only. Short-MTU fragmented
  E719/E71A layouts are not implemented. Unknown marker/advertisement tails
  and V1 padding remain opaque. Advertisement flags follow BleUtil's
  parseBleBroadcastPact; omission is not negative encryption evidence.
seq: []
types:
  advertisement:
    seq:
      - id: flags
        type: u1
      - id: magic
        size: 2
      - id: pact_type
        type: u2
      - id: pact_code
        type: u1
      - id: unknown_tail
        size-eos: true
  marker:
    seq:
      - id: format
        type: u1
      - id: version
        type: u1
      - id: flag
        type: u1
        if: format == 2
      - id: pact_type
        type: u2
        if: format == 2
      - id: pact_code
        type: u1
        if: format == 2
      - id: unknown_tail
        size-eos: true
  v1_handshake:
    seq:
      - id: magic
        type: u1
      - id: opcode
        type: u1
      - id: body
        size: 16
      - id: unknown_padding
        size: 1
      - id: checksum
        type: u1
  v2_request:
    seq:
      - id: magic
        type: u1
      - id: opcode
        type: u1
      - id: direction
        type: u1
      - id: nonce
        size: 12
      - id: tag_length
        type: u1
      - id: sealed
        size: 24
  v2_response:
    seq:
      - id: magic
        type: u1
      - id: opcode
        type: u1
      - id: status
        type: u1
      - id: nonce
        size: 12
      - id: sealed
        size: 35
  v2_identity:
    seq:
      - id: iv_key
        size: 8
      - id: sku
        size: 5
      - id: mac_wire_order
        size: 6
  v2_frame:
    seq:
      - id: counter
        type: u4
      - id: sealed
        size-eos: true
