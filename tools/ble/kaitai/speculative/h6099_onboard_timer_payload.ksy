meta:
  id: h6099_onboard_timer_payload
  title: H6099 onboard timer logical payloads (documentation only)
doc: |
  SPECULATIVE H6099, support issue #258.  Hypothesis: Govee Android 7.6.01
  H6099 timer payloads use opcode 0x23 with a 17-byte read-all reply body (frame
  offsets 2 through 18) containing one ignored prefix byte and four four-byte
  timer records.  Nested types describe the one-byte query and five-byte write
  body without BLE framing.
  Unknowns: exact-device captures, timer index range, repeat bit meanings,
  ignored reply prefix, single-index reply layout, and firmware compatibility.
  Preserve packed fields without inferred enums or validity constraints.
  No runtime queries, writes, clock sync, or scheduling; use HA automations.
seq:
  - id: unknown_prefix
    type: u1
  - id: timers
    type: timer_record
    repeat: expr
    repeat-expr: 4
types:
  timer_record:
    seq:
      - id: enable_and_type_raw
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: repeat_raw
        type: u1
  query_payload:
    doc: Index 0xff requests all timer slots; other index ranges are unqualified.
    seq:
      - id: index
        type: u1
  write_payload:
    seq:
      - id: index
        type: u1
      - id: timer
        type: timer_record
