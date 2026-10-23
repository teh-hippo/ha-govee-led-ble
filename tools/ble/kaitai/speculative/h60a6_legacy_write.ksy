meta:
  id: h60a6_legacy_write
  title: H60A6 Pact 1/1 whole-device colour
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H60A6 support for issue #402.  Compatibility hypothesis:
  Pact 1/1 uses the whole-device 0D colour operation, without a segment mask.
  Kelvin writes use a white direct-RGB prefix and a companion RGB value.
  This route is independent of native panel/ring enable flags and is not
  used for the owner's segmented revision, which ignores legacy colour
  writes.  Unknown suffix bytes, physical revision behaviour and captures
  for explicit Pact 1/1 remain unresolved.
seq:
  - id: header
    contents: [0x33, 0x05, 0x0d]
  - id: rgb_direct
    type: govee_shared::rgb
  - id: kelvin
    type: u2
  - id: rgb_preview
    type: govee_shared::rgb
  - id: unknown_tail
    size: 8
  - id: checksum
    type: u1
