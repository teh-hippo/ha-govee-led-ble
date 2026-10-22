meta:
  id: h6099_dreamview_group
  title: H6099 MovieFeastV2 authored membership
  endian: be
doc: |
  SPECULATIVE H6099 issue #258.  Android 7.6.01 goods type 191 selects the
  MovieFeastV2 group upload over A3 type 0x50 with at most seven sub-devices.
  The payload prefixes a member count followed by the member records below.
  MAC bytes use reversed display order, and name bytes use UTF-8.  cmd_ver is
  supplied externally, never inferred.  The protocol maps UI areas 1..20 onto
  wire values 1..10; zero is unassigned and 0xff disables an area.  Area counts
  must be supplied explicitly.  Zero-area records and single-area disabled
  behaviour remain unresolved and are not enabled.  No membership readback,
  official-app capture, or owner qualification exists for H6099.  A successful
  upload is not confirmation.
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
    value: 0x50
types:
  member:
    seq:
      - id: is_rgbic
        type: u1
      - id: identity_kind
        type: u1
        enum: identity_kind
      - id: cmd_ver
        type: u1
      - id: reversed_mac
        size: 6
        if: identity_kind == identity_kind::mac
      - id: name_len
        type: u1
        if: identity_kind == identity_kind::name
      - id: name_bytes
        size: name_len
        if: identity_kind == identity_kind::name
      - id: area_count
        type: u1
      - id: area_values
        type: u1
        repeat: expr
        repeat-expr: area_count
enums:
  identity_kind:
    0: mac
    1: name
