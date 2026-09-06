meta:
  id: h6102_common
  title: Govee H6102 shared BLE wire datatypes
  endian: le
doc: |
  SPECULATIVE H6102 schema for #115.
  Evidence source class: public exact-model packet tables and independent
  working implementations; no attributable official-app capture.
  Compatibility hypothesis: H6102 extended 0x15/0x01 RGB commands encode the
  observed region selection as a little-endian 16-bit value.
  Unresolved assumptions: the accepted mask domain, including zero and bit 15,
  the physical region mapping, and firmware applicability are not captured.
types:
  region_mask_15:
    seq:
      - id: bits
        type: u2le
