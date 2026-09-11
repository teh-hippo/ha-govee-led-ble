meta:
  id: synthetic_mixed_status_reply
  title: Synthetic shared power and four-slot segment status (fixture only)
  endian: le
  imports:
    - /status_reply
    - /govee_segment_page
doc: |
  SPECULATIVE test-only composition for issue #278, not a device protocol claim.
  Reuses H617A power status with the fixture's 14-segment, four-slot layout.
  These are the only readable domains of the synthetic integration profile.
  This does not extend H66A0 evidence or enable any runtime model.
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
        'status_domain::segments': govee_segment_page(14, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0xa5: segments
