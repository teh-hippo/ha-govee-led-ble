meta:
  id: scene_body
  title: Govee H617A reassembled scene / rgbicv2 record-container body (decode-only)
  endian: le
doc: |
  The reassembled 0xA3 multi-frame body (host reassembles the 17-byte chunks; the
  framing/terminator is transport, not modelled here). On-wire layout:
    01 <linecount> <scene_type> <record_count> [<rec_len> <rec_data>]... <zero padding>
  This revision validates the record FRAMING only: the record count, the
  length-prefixed records, and that the remainder is transport zero-padding to the
  17-byte A3 chunk boundary (outside the records). Record internals (type-switched
  fields, brightness sub-records, colour sub-block) are decoded in later revisions.
  Re-verified against captured Aurora bodies; captures are ground truth.
  Models scene_type 2 (rgbicv2) bodies only; other A3 bodies (music 0x41,
  Flat/Sketch/Vibrant 0x03) use different grammars and must not be routed here.
seq:
  - id: marker
    contents: [0x01]
    doc: raw 0x01, generic build_a3_multi body marker
  - id: linecount
    type: u1
    doc: A3 data-chunk count (transport), raw
  - id: scene_type
    type: u1
    enum: scene_type
    doc: raw scene-type selector
  - id: record_count
    type: u1
    doc: number of length-prefixed records that follow
  - id: records
    type: record
    repeat: expr
    repeat-expr: record_count
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: transport zero padding to the A3 chunk boundary; grammar-enforced all-zero
enums:
  scene_type:
    0: scene_v0
    1: scene_v1
    2: rgbicv2
types:
  record:
    seq:
      - id: rec_len
        type: u1
        doc: number of record bytes that follow this length byte
      - id: body
        type: record_body
        size: rec_len
  record_body:
    doc: |
      rgbicv2 record internals, offsets from the record length byte (r0). Only the
      wire-verified prefix and the brightness sub-records are field-decoded here; the
      trailing colour sub-block (which carries the per-record speed byte, per the
      Brilliant colour-param1 finding) is left opaque (INHERITED, not yet decoded).
    seq:
      - id: flags
        type: u1
        doc: r1, packed nibbles (0x00 in the captures seen)
      - id: record_type
        type: u1
        doc: r2, mode selector 0-3 (selects the meaning of r3-r4)
      - id: val1
        type: u1
        doc: r3, type-dependent value (raw)
      - id: val2
        type: u1
        doc: r4, type-dependent value (raw)
      - id: r5
        type: u1
        doc: r5, raw (meaning not yet verified)
      - id: bright_count
        type: u1
        doc: r6, number of 6-byte brightness records that follow
      - id: brightness
        type: bright_record
        repeat: expr
        repeat-expr: bright_count
      - id: colour_and_rest
        size-eos: true
        doc: colour sub-block + remainder; opaque (INHERITED). Carries the speed byte.
  bright_record:
    doc: 6-byte brightness record; the first two bytes are the relative-brightness interval (upper, lower).
    seq:
      - id: interval_upper
        type: u1
      - id: interval_lower
        type: u1
      - id: rest
        size: 4
