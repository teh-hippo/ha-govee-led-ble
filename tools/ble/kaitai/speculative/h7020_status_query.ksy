meta:
  id: h7020_status_query
  title: H7020 candidate status queries
  endian: le
  imports:
    - ../status_query
doc: |
  SPECULATIVE H7020, support PR #363. Candidate queries reuse the shared
  power, brightness, mode and identity layouts. AA0F reads configured string
  count; AA41 reads power-off memory. A5 pages contain three bulb records,
  requiring five or ten queries according to freshly confirmed configuration.
  The selected mode query is AA0501; the shared structural type also retains
  the zero-selector form without claiming exact-model acceptance.
  Unresolved assumptions: exact-model captures have not qualified all replies,
  page ordering, two-string behaviour or concurrent configuration changes.
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
        'query_domain::configured_strings': status_query::zero_body
        'query_domain::power_off_memory': status_query::zero_body
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
    0x0f: configured_strings
    0x41: power_off_memory
    0xa5: segments
types:
  segment_query_body:
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 10
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
