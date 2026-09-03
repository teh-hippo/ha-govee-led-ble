meta:
  id: h6179_status_query
  title: Govee H6179 speculative "aa" status-query envelope
  endian: le
doc: |
  SPECULATIVE H6179 compatibility hypothesis: exact-SKU status queries use a
  20-byte 0xaa envelope and the candidate domain and selector bytes represented
  below.
  Unresolved assumptions: no exact-model capture verifies the domain meanings,
  mode, hardware, or timer selectors, opaque body bytes, or XOR checksum byte.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: status_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'status_domain::power': opaque_body
        'status_domain::brightness': opaque_body
        'status_domain::mode': mode_query_body
        'status_domain::firmware': opaque_body
        'status_domain::hardware': hardware_query_body
        'status_domain::limit': opaque_body
        'status_domain::sleep': opaque_body
        'status_domain::wake': opaque_body
        'status_domain::timers': timers_query_body
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
        enum: mode_query_selector
      - id: opaque
        size-eos: true
  hardware_query_body:
    seq:
      - id: selector
        type: u1
        enum: hardware_query_selector
      - id: opaque
        size-eos: true
  timers_query_body:
    seq:
      - id: selector
        type: u1
        enum: timers_query_selector
      - id: opaque
        size-eos: true
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: mode
    0x06: firmware
    0x07: hardware
    0x0e: limit
    0x11: sleep
    0x12: wake
    0x23: timers
  mode_query_selector:
    0x01: current
  hardware_query_selector:
    0x03: primary
  timers_query_selector:
    0xff: all
