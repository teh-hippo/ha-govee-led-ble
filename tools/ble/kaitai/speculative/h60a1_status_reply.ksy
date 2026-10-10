meta:
  id: h60a1_status_reply
  title: Govee H60A1 ceiling light AA status
  endian: le
  imports:
    - ../govee_segment_page
doc: |
  SPECULATIVE H60A1 manual experimental support, reporter's H60A support request.
  Compatibility hypothesis: shared AA power/identity envelope and fourteen
  logical segments in four four-slot A5 pages. Reporter immutable fork
  cedhuf/ha-govee-led-ble f8d4267309e7bac38460c728e05616d07f879b3e,
  docs/h60a-support-findings.md and tests/test_h60a_protocol.py: HW 1.04.03,
  FW 1.02.20 power and page-four literal, 2026-10-09/10 decrypted owner sessions.
  Android 7.6.01 full/sources/com/govee/pact_h60a0/pact/Support.java:
  185-214,238-240 identifies fourteen records and four per group;
  base2light/kt/general_controller/Controller4ColorInfoByGroup.java:173-187
  consumes only the meaningful brightness/RGB records. Unused slots are opaque.
  Unresolved: other revisions, identity response presence, unused bytes,
  rendered brightness vs register state, mode and Kelvin readback. Runtime
  gates segment use separately; neither brightness nor mode is a read domain.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: aa_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'aa_domain::power': power_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::segments': govee_segment_page(14, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x06: fw_version
    0x07: hw_version
    0xa5: segments
types:
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  hw_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
