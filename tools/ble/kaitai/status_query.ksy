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
        'query_domain::camera_install': zero_body
        'query_domain::ic_segment_count': zero_body
        'query_domain::gradual_change': zero_body
        'query_domain::segments': segment_query_body
        'query_domain::display_setting': display_setting_query_body
  - id: checksum
    type: u1
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    # A bare presence probe for the removable camera module. It answers only with the
    # module attached, which is what makes camera capabilities a runtime question.
    0x32: camera_install
    # 00 <ic count u16be> <app segment count>. The third byte is only trustworthy where it
    # has been cross-checked -- an H6199 answers 38 here and 38 is NOT its segment count.
    0x40: ic_segment_count
    0xa3: gradual_change
    0xa5: segments
    0xa9: display_setting
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
  display_setting_query_body:
    doc: |
      A bare read of one 0xa9 register: the sub-command byte and nothing else. Confirmed on an
      H66A0 on 2026-08-23, which answered subs 01, 04, 09, 0a, 0b, 10 and 11 in the
      setting/len/values shape of status_reply::display_setting_body.
    seq:
      - id: setting
        type: u1
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
