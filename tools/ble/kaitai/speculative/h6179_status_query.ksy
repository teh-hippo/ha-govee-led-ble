meta:
  id: h6179_status_query
  title: Govee H6179 speculative "aa" status-query envelope
  endian: le
doc: |
  SPECULATIVE H6179 #227 compatibility hypothesis: exact-SKU status queries use a
  20-byte 0xaa envelope and the candidate domain and selector bytes represented
  below.
  Unresolved assumptions: no exact-model capture verifies the domain meanings,
  mode, hardware, or timer selectors, opaque body bytes, or XOR checksum byte.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        '0x01': opaque_body
        '0x04': opaque_body
        '0x05': mode_query_body
        '0x06': opaque_body
        '0x07': hardware_query_body
        '0x0e': opaque_body
        '0x11': opaque_body
        '0x12': opaque_body
        '0x23': timers_query_body
  - id: checksum
    type: u1
types:
  opaque_body:
    seq:
      - id: opaque
        size-eos: true
  mode_query_body:
    seq:
      - id: selector
        type: u1
      - id: opaque
        size-eos: true
  hardware_query_body:
    seq:
      - id: selector
        type: u1
      - id: opaque
        size-eos: true
  timers_query_body:
    seq:
      - id: selector
        type: u1
      - id: opaque
        size-eos: true
