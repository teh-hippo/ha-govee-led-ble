meta:
  id: govee_rgb_segment_page
  title: Legacy RGB-only Govee segment page
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE RGB-only pages, H6125 #117 and H6072 #486.
  Compatibility hypothesis: legacy A2 pages contain a one-based group and
  model-declared RGB-only slots, with no brightness byte. Only the declared
  segment count is meaningful. Unused slots and suffix bytes remain opaque;
  their values and physical mapping are unqualified.
params:
  - id: segment_count
    type: u1
  - id: group_size
    type: u1
seq:
  - id: group
    type: u1
    valid:
      min: 1
      max: (segment_count + group_size - 1) / group_size
  - id: segments
    type: segment_record
    repeat: expr
    repeat-expr: num_segments
  - id: unknown_tail
    size-eos: true
instances:
  num_segments:
    value: 'group * group_size <= segment_count ? group_size : segment_count - (group - 1) * group_size'
types:
  segment_record:
    seq:
      - id: colour
        type: govee_shared::rgb
