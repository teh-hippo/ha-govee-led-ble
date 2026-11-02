meta:
  id: h6046_status_query
  title: Govee H6046 status queries
  endian: le
doc: |
  H6046.
  Evidence class: exact-model behavioural audit, not device evidence or hardware
  qualification. Known Pact 1/1 and 2/1 use these 20-byte AA queries.
  XOR of bytes 0..18 occupies byte 19 and is checked by the transport.
  Replies are described by h6046_status_reply. Segment groups request four
  records each, with only two meaningful records in group 3.
  Unresolved assumptions: unreported revisions, query timing and unsupported
  identity envelope variants. No power-off-memory query permission is implied.
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
        'query_domain::power': zero_body
        'query_domain::brightness': zero_body
        'query_domain::colour_mode': zero_body
        'query_domain::firmware': zero_body
        'query_domain::hardware': hardware_query_body
        'query_domain::identity': zero_body
        'query_domain::subordinate_20': zero_body
        'query_domain::subordinate_21': zero_body
        'query_domain::bar_enable': zero_body
        'query_domain::segments': segment_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x14: identity
    0x20: subordinate_20
    0x21: subordinate_21
    0x33: bar_enable
    0xa5: segments
types:
  zero_body:
    seq:
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  hardware_query_body:
    seq:
      - id: selector
        contents: [0x03]
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
  segment_query_body:
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 3
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
