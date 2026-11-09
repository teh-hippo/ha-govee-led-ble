meta:
  id: h6125_legacy_segment_query
  title: Govee H6125 legacy RGB-only segment query
doc: |
  H6125 and older H619A revisions share this A2 query encoding.
  Compatibility hypothesis: legacy segment readback queries up to four groups;
  the effective profile restricts H619A to three for ten logical segments.
  The command carries a one-based group and
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
