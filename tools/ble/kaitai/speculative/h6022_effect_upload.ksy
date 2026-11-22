meta:
  id: h6022_effect_upload
  title: Govee H6022 A3 effect upload envelope (decode-only)
  imports:
    - ../govee_common
doc: |
  SPECULATIVE H6022 exact-model upload envelope.  Subtype 0x04 carries ordinary
  DIY and legacy catalogue scene bodies.  Those paths share leading byte 0x00
  for some valid content, so the upload envelope deliberately preserves the
  body as opaque data.  Subtype 0x58 carries professional graffiti scenes.
  Semantic decoding requires the operation's authored content or catalogue
  identity, never a guess from the first payload byte.
seq:
  - id: header
    type: govee_common::a3_header
  - id: upload_type
    type: u1
    valid:
      any-of: [0x04, 0x58]
  - id: data
    size-eos: true
