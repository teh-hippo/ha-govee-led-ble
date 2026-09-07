meta:
  id: h61f5_status_reply
  title: H61F5 and H1A42 exact-model status grammar
  endian: le
  imports:
    - /govee_segment_page
    - /status_reply
doc: |
  SPECULATIVE H61F5 status grammar, also reused by H1A42 where captured
  replies have the same five-segment, four-slot paging. Unused final-page
  slots remain opaque because their semantics are not established.
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
        'status_domain::power': status_reply::power_body
        'status_domain::brightness': status_reply::brightness_body
        'status_domain::colour_mode': status_reply::colormode_body
        'status_domain::firmware': status_reply::version_body
        'status_domain::hardware': status_reply::hw_version_body
        'status_domain::subordinate_20': status_reply::version_body
        'status_domain::subordinate_21': status_reply::version_body
        'status_domain::ic_segment_count': ic_segment_count_body
        'status_domain::multi_effect': status_reply::multi_effect_body
        'status_domain::segments': govee_segment_page(5, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x20: subordinate_20
    0x21: subordinate_21
    0x40: ic_segment_count
    0xa3: multi_effect
    0xa5: segments
types:
  ic_segment_count_body:
    seq:
      - id: ic_count
        type: u2be
      - id: segment_count
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
