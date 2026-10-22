meta:
  id: govee_rgb_segment_page
  title: Legacy RGB-only Govee segment page
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: legacy A2 pages contain a one-based group and four
  RGB-only slots, with no brightness byte.  Only the declared segment count is
  meaningful.  Unused slots and the final four bytes remain opaque; their
  values and physical mapping are unqualified.
params:
  - id: segment_count
    type: u1
seq:
  - id: group
    type: u1
    valid:
      min: 1
      max: (segment_count + 3) / 4
  - id: segments
    type: segment_record
    repeat: expr
    repeat-expr: num_segments
  - id: unknown_tail
    size-eos: true
instances:
  num_segments:
    value: 'group * 4 <= segment_count ? 4 : segment_count - (group - 1) * 4'
types:
  segment_record:
    seq:
      - id: colour
        type: govee_shared::rgb
