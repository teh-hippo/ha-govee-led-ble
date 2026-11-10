meta:
  id: h6181_status_query
  title: Govee H6181 basic status queries
  endian: be
doc: |
  SPECULATIVE H6181 candidate AA queries. Mode uses selector 01 and hardware
  uses selector 03. Unknown suffixes are retained. The final byte is XOR.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: query_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'query_domain::colour_mode': colour_mode_query_body
        'query_domain::hardware': hardware_query_body
        _: zero_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
types:
  zero_body:
    seq:
      - id: zeros
        type: u1
        repeat: expr
        repeat-expr: 17
  colour_mode_query_body:
    seq:
      - id: selector
        type: u1
      - id: zeros
        type: u1
        repeat: expr
        repeat-expr: 16
  hardware_query_body:
    seq:
      - id: selector
        size: 1
      - id: zeros
        type: u1
        repeat: expr
        repeat-expr: 16
