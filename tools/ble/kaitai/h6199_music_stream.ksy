meta:
  id: h6199_music_stream
  title: Govee H6199 phone-microphone music stream frame (a5 02 83, 7 bytes)
  endian: le
doc: |
  H6199 seven-byte microphone stream frame. The final byte is the low eight bits of the sum of bytes 0 through 5.
seq:
  - id: magic
    contents: [0xa5, 0x02, 0x83]
  - id: red
    type: u1
  - id: green
    type: u1
  - id: blue
    type: u1
  - id: checksum
    type: u1
