meta:
  id: h66a0_status_reply
  title: H66A0 segment status hypothesis (fixture only)
  endian: le
  imports:
    - /govee_segment_page
doc: |
  SPECULATIVE H66A0, issue #272 concern 3. The reported official-app frames
  aa a5 01 64e54444 64ffae54 64ffae54 64cf2e2e 24 and
  aa a5 04 64dc3b3b 64e54444 00000000 00000000 32 support a four-slot
  brightness/RGB page hypothesis with reported 14-segment, 4+4+4+2 paging.
  Unknowns: pages 2 and 3 have not been supplied, physical segment ordering
  and readback behaviour remain unqualified, and unused final-page slots
  have no established meaning or zero constraint. Preserve their raw octets.
  No other status domains or models are inferred. This root is for generated
  fixture tests only, not runtime support, discovery, or a whole-family alias.
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
        'status_domain::segments': govee_segment_page(14, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0xa5: segments
