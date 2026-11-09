meta:
  id: h60b0_status_query
  title: H60B0 candidate ordinary status queries
  imports:
    - ../status_query
doc: |
  SPECULATIVE: Exact-model ordinary queries, not confirmed by device traffic.
  The source information request is separate from the current-mode request.
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
        'query_domain::power_on_behaviour': status_query::zero_body
        'query_domain::source_info': status_query::zero_body
        'query_domain::segments': status_query::segment_query_body
        'query_domain::pact': status_query::zero_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x41: power_on_behaviour
    0x42: source_info
    0xa5: segments
    0xef: pact
