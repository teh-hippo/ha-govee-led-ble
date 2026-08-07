meta:
  id: h6199_wifi_provision
  title: Govee H6199 "a1 11" Wi-Fi provisioning frame (decode-only)
  endian: be
doc: |
  H6199 20-byte Wi-Fi fragment. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0xa1]
  - id: sub_opcode
    type: u1
    valid: 0x11
  - id: index
    type: u1
  - id: payload
    size: 16
  - id: checksum
    type: u1
instances:
  is_header:
    value: index == 0
  is_terminator:
    value: index == 0xff
  data_frame_count:
    value: payload[0]
    if: index == 0
