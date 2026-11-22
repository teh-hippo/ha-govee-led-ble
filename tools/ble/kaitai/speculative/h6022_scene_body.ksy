meta:
  id: h6022_scene_body
  title: Govee H6022 native-scene body envelope (decode-only)
doc: |
  SPECULATIVE H6022 exact-model catalogue body.  Public catalogue records and
  the recorded H6022 owner revision distinguish two opaque envelope markers:
  0x00 legacy Type-4 bodies uploaded through A3 subtype 0x04, and 0x41
  professional graffiti bodies uploaded through A3 subtype 0x58.  Preserve all
  remaining bytes exactly until each payload family has independently
  established field semantics.
seq:
  - id: marker
    type: u1
    valid:
      any-of: [0x00, 0x41]
  - id: data
    size-eos: true
