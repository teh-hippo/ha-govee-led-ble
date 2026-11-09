meta:
  id: h1771_status_query
  title: H1771 candidate ordinary status queries
  endian: le
doc: |
  SPECULATIVE: H1771 snapshot and segment queries reconstructed from model
  behaviour, not confirmed by device traffic.  Other query domains are not
  inferred from these layouts.  Unknown suffix bytes remain opaque.
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
        'query_domain::power': opaque
        'query_domain::brightness': opaque
        'query_domain::colour_mode': mode_query
        'query_domain::segments': segment_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0xa5: segments
types:
  opaque:
    seq:
      - id: unknown_tail
        size-eos: true
  mode_query:
    seq:
      - id: selector
        type: u1
      - id: unknown_tail
        size-eos: true
  segment_query_body:
    seq:
      - id: group
        type: u1
      - id: unknown_tail
        size-eos: true
