meta:
  id: h6125_brightness_write
  title: Govee H6125 raw-brightness write
  endian: le
doc: |
  Captured H6125 20-byte brightness frame. The value is a raw device register on
  hardware family 1 and a percentage on later hardware families. The final byte
  is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0x33, 0x04]
  - id: value
    type: u1
  - id: padding
    contents: [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
  - id: checksum
    type: u1
