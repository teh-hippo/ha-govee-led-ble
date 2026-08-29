meta:
  id: h6125_colour_mode_query
  title: Govee H6125 active-mode query
  endian: le
doc: |
  Captured H6125 20-byte active-mode query. The selector differs from the
  H617A query. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0xaa, 0x05, 0x01]
  - id: padding
    contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
  - id: checksum
    type: u1
