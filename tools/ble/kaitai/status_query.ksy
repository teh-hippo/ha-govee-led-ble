meta:
  id: status_query
  title: Govee H617A "aa" status-query envelope
  endian: le
doc: |
  H617A 20-byte status query. The final byte is the XOR of bytes 0 through 18.
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
    doc: Selects one of five three-segment reply groups.
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 5
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
