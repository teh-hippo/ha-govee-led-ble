meta:
  id: h60a6_status_reply
  title: Govee H60A6 segmented ceiling light AA status
  endian: le
  imports:
    - ../govee_segment_page
doc: |
  SPECULATIVE H60A6 manual experimental support, reporter's H60A support request.
  Compatibility hypothesis: shared AA power/identity envelope and thirteen
  logical segments in four four-slot A5 pages on the segmented revision.
  Reporter immutable fork cedhuf/ha-govee-led-ble
  f8d4267309e7bac38460c728e05616d07f879b3e, docs/h60a-support-findings.md
  and tests/test_h60a_protocol.py: HW 1.04.03, FW 1.00.41 power and page-one/
  page-four literals, 2026-10-09/10 decrypted owner sessions.
  Android 7.6.01 full/sources/com/govee/pact_h60a0/pact/Support.java:
  209-214,238-240,345-346,489-498: Pact 1/1 has one zone; 1/2+ has thirteen,
  1/3+ adds masked Kelvin. base2light/kt/general_controller/
  Controller4ColorInfoByGroup.java:173-187 consumes only meaningful records.
  Unresolved: legacy one-zone reply layout, other revisions, identity presence,
  unused bytes, rendered brightness vs register state, mode and Kelvin readback.
  Runtime gates segment use separately; brightness and mode remain opaque.
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
        'aa_domain::segments': govee_segment_page(13, 4, false)
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
