meta:
  id: h607c_dreamview_group
  title: H607C candidate Music DreamView membership
  endian: le
doc: |
  H607C.
  Compatibility hypothesis: Music DreamView V2 uploads a member count
  and explicit identity records under A3 command 60. Each record ends
  with a scalar area count, not the camera protocol's area-value vector.
  Mark and command version are supplied explicitly. MAC bytes are reversed;
  names use byte lengths. Member compatibility and group results require
  hardware qualification. No membership readback is implied.
seq:
  - id: num_members
    type: u1
  - id: members
    type: member
    repeat: expr
    repeat-expr: num_members
  - id: unknown
    size-eos: true
instances:
  group_type:
    value: 0x60
types:
  member:
    seq:
      - id: mark
        type: u1
      - id: identity_kind
        type: u1
        enum: identity_kind
      - id: cmd_ver
        type: u1
      - id: reversed_mac
        size: 6
        if: identity_kind == identity_kind::mac
      - id: len_name_bytes
        type: u1
        if: identity_kind == identity_kind::name
      - id: name_bytes
        size: len_name_bytes
        if: identity_kind == identity_kind::name
      - id: area_num
        type: u1
enums:
  identity_kind:
    0: mac
    1: name
