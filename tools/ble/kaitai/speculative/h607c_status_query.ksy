meta:
  id: h607c_status_query
  title: H607C candidate ordinary status queries
  endian: le
  imports:
    - ../status_query
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: ordinary power, brightness, mode and identity
  requests share the common query bodies. Native settings have separate
  selector-zero and device-info queries in h607c_control.
  Segment query coverage and reply timing remain unqualified.
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
        'query_domain::power': status_query::zero_body
        'query_domain::brightness': status_query::zero_body
        'query_domain::colour_mode': status_query::colour_mode_query_body
        'query_domain::firmware': status_query::zero_body
        'query_domain::hardware': status_query::hardware_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
