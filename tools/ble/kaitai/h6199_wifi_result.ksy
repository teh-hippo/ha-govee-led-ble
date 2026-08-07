meta:
  id: h6199_wifi_result
  title: Govee H6199 "ee 11" Wi-Fi association result (decode-only)
  endian: be
doc: |
  H6199 20-byte Wi-Fi association result. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0xee]
  - id: sub_opcode
    type: u1
    valid: 0x11
  - id: status
    type: u1
    enum: outcome
  - size: 16
  - id: checksum
    type: u1
enums:
  outcome:
    0x00: associated
    0x01: not_connected
