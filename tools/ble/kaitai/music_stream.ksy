meta:
  id: music_stream
  title: Govee H617A phone-microphone music stream frame (a5 02 83, 7 bytes)
  endian: le
  imports:
    - govee_shared
    - govee_common
doc: |
  H617A seven-byte microphone stream frame. The final byte is the low eight bits of the sum of bytes 0 through 5.
seq:
  - id: opcode
    contents: [0xa5]
  - id: stream_sub
    contents: [0x02]
  - id: stream_mode
    contents: [0x83]
  - id: colour
    type: govee_shared::rgb
  - id: checksum
    type: u1
instances:
  checksum_expected:
    value: '(0xa5 + 0x02 + 0x83 + colour.r + colour.g + colour.b) % 256'
