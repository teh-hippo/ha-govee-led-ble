meta:
  id: h6072_legacy_query
  title: H6072 candidate legacy segment queries
  endian: le
  imports:
    - ../status_query
    - h6072_status_query
doc: |
  H6072.
  Compatibility hypothesis: legacy revisions query three RGB-only A2 groups
  and share basic query bodies. Exact-model evidence and timing are unqualified.
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
        'query_domain::multi_effect': status_query::zero_body
        'query_domain::segments': h6072_status_query::segment_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0xa2: segments
    0xa3: multi_effect
