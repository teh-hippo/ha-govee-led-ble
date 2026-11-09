meta:
  id: h605c_gradual
  title: H605C independently addressable gradual register
doc: |
  SPECULATIVE H605C read/write register. Both registered Pact revisions
  use the shared single-register A3 gradual codec. This is not an A3
  multi-packet upload: header 33 writes, header aa queries or reports.
  Only value 1 means enabled. A command acknowledgement is not readback.
  The write uses a flag followed by zero-filled outbound space; queries
  contain no flag. Replies retain the entire uninterpreted suffix.
params:
  - id: is_query
    type: bool
seq:
  - id: header
    type: u1
    enum: header
  - id: opcode
    contents: [0xa3]
  - id: flag
    type: u1
    if: not is_query
  - id: unknown_tail
    size: 'is_query ? 17 : 16'
  - id: checksum
    type: u1
enums:
  header:
    0x33: write
    0xaa: read
