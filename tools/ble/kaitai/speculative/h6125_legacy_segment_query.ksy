meta:
  id: h6125_legacy_segment_query
  title: Govee H6125 legacy RGB-only segment query
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: legacy segment readback queries four A2 groups
  for fifteen logical segments.  The command carries a one-based group and
  zero-filled request bytes.  Reply padding and hardware acceptance remain
  unqualified and are not constrained by this writer.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: query_domain
    valid: query_domain::segments
  - id: group
    type: u1
    valid:
      min: 1
      max: 4
  - id: padding
    size: 16
  - id: checksum
    type: u1
enums:
  query_domain:
    0xa2: segments
