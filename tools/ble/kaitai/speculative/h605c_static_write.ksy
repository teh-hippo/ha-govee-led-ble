meta:
  id: h605c_static_write
  title: H605C static RGBIC colour, Kelvin and brightness commands
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE exact-model static command contract for H605C Pact 1/1 and 1/2.
  Fourteen logical selections use a little-endian two-byte mask. Whole-strip
  selection is ff 3f. A publicly reported H605C also renders whole-strip RGB
  and nominal 3000/6500 K with ff 7f; this does not establish a fifteenth segment.
  Physical IC count is independent of the fourteen static selections.
  The common RGBIC command adapter emits this structure. The generic
  33 05 02 RGB command is not an alternative static-colour route.
  Kelvin uses white direct RGB, big-endian Kelvin and its companion RGB tint.
  RGB clears Kelvin and tint. The basic mode reply is not RGB readback.
  Grouped colour/brightness reads are separate. Acknowledgements confirm
  acceptance, not rendering or the accuracy of nominal colour temperature.
  Uncertain suffix bytes are retained. The final byte is XOR of bytes 0..18.
seq:
  - id: header
    contents: [0x33, 0x05, 0x15]
  - id: operation
    type: u1
    enum: operation
  - id: body
    size: 15
    type:
      switch-on: operation
      cases:
        'operation::colour': colour
        'operation::brightness': brightness
  - id: checksum
    type: u1
enums:
  operation:
    1: colour
    2: brightness
types:
  colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: tint
        type: govee_shared::rgb
      - id: mask
        type: u2le
      - id: unknown_tail
        size-eos: true
  brightness:
    seq:
      - id: percent
        type: u1
      - id: mask
        type: u2le
      - id: unknown_tail
        size-eos: true
