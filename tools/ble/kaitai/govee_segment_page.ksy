meta:
  id: govee_segment_page
  title: Shared Govee segment readback page
  endian: le
  imports:
    - govee_shared
doc: |
  Brightness/RGB records with model-declared cardinality. Wire slots need not
  all represent segments. Unused octets are retained, never inferred from black
  or off records. Only models with evidenced zero padding enforce zeroes.
params:
  - id: segment_count
    type: u1
  - id: group_size
    type: u1
  - id: unused_must_be_zero
    type: bool
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
  - id: unused
    doc: Opaque unused slot octets, including unexpected nonzero values where allowed.
    type: u1
    repeat: expr
    repeat-expr: (4 - num_segments) * 4
    valid:
      expr: not unused_must_be_zero or _ == 0
instances:
  num_segments:
    doc: Meaningful record count, independent of unused wire slots and record values.
    value: 'group * group_size <= segment_count ? group_size : segment_count - (group - 1) * group_size'
types:
  segment_record:
    seq:
      - id: brightness
        type: u1
      - id: colour
        type: govee_shared::rgb
