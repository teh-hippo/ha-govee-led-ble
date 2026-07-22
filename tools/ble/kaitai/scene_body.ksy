meta:
  id: scene_body
  title: Govee H617A reassembled scene / rgbicv2 record-container body (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body (host reassembles the 17-byte chunks; the
  framing/terminator is transport, not modelled here). On-wire layout:
    01 <linecount> <scene_type> <record_count> [<rec_len> <rec_data>]... <zero padding>
  This revision validates the record FRAMING and the wire-verified record prefix;
  the trailing colour sub-block (which carries the per-record speed byte) is left
  opaque. Re-verified byte-exact against captured Aurora bodies; captures are
  ground truth. Models scene_type 2 (rgbicv2) bodies only; other A3 bodies (music
  0x41, Flat/Sketch/Vibrant 0x03) use different grammars and must not be routed here.
  Every field carries one evidence tag in its doc: [CONFIRMED_LIVE] position and
  meaning proven by a round-tripped capture; [INFERRED] reasoned, meaning not
  isolated by a capture; [INHERITED] modelled from write-side/docs, no confirming
  capture (pessimistic default). Proven byte-exact on Aurora (record_count 2) and
  Forest (record_count 3, record_type 1/2/0) type-2 bodies: the record FRAMING
  generalises, but the record-internal field meanings (record_type/val1/val2/r5) are
  not changed by any app control, so they cannot be isolated and stay conservative.
seq:
  - id: header
    type: govee_common::a3_header
    doc: '[CONFIRMED_LIVE] shared A3 body header 01 <linecount>; scene bodies span whole 17-byte chunks (Aurora linecount == len/17)'
  - id: scene_type
    type: u1
    enum: scene_type
    valid:
      eq: scene_type::scene_v2
    doc: '[CONFIRMED_LIVE] catalogue scene_type selector (frame offset 2); values 0/1/2 exist and select DISTINCT body grammars (Sunrise=0, Halloween=1 code 0x0495, Aurora=2 code 0x0874), matching the frozen catalogue scene_type field. Only type 2 (rgbicv2) is modelled here; a type-1 body does not follow this record framing (proven: the Halloween body misparses, record_count reads 0x83). The valid guard fails the grammar closed on non-type-2 bodies.'
  - id: record_count
    type: u1
    doc: '[CONFIRMED_LIVE] number of length-prefixed records that follow'
  - id: records
    type: record
    repeat: expr
    repeat-expr: record_count
    doc: '[CONFIRMED_LIVE] record_count length-prefixed records'
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: '[CONFIRMED_LIVE] transport zero padding to the A3 chunk boundary; grammar-enforced all-zero'
enums:
  scene_type:
    0: scene_v0
    1: scene_v1
    2: scene_v2
types:
  record:
    seq:
      - id: rec_len
        type: u1
        doc: '[CONFIRMED_LIVE] number of record bytes that follow this length byte'
      - id: body
        type: record_body
        size: rec_len
        doc: '[CONFIRMED_LIVE] rec_len bytes of record body'
  record_body:
    doc: |
      rgbicv2 record internals, offsets from the record length byte (r0). Only the
      wire-verified prefix and the brightness sub-records are field-decoded here; the
      trailing colour sub-block (which carries the per-record speed byte, per the
      Brilliant colour-param1 finding) is left opaque.
    seq:
      - id: flags
        type: u1
        doc: '[INFERRED] r1, packed nibbles (0x00 in the captures seen); meaning reasoned'
      - id: record_type
        type: u1
        doc: '[INFERRED] r2, record-type selector; values 0/1/2 observed across records (Aurora both 0; Forest 1/2/0). Selects the meaning of val1/val2, but no app control changes it, so the per-value meaning is not isolated.'
      - id: val1
        type: u1
        doc: '[INFERRED] r3, type-dependent value (raw); observed 0 and 15'
      - id: val2
        type: u1
        doc: '[INFERRED] r4, type-dependent value (raw); observed 1, 3, 5, 10'
      - id: r5
        type: u1
        doc: '[INFERRED] r5, raw; constant 0x02 in every captured record (Aurora + Forest); meaning not isolated'
      - id: bright_count
        type: u1
        doc: '[CONFIRMED_LIVE] r6, number of 6-byte brightness records that follow'
      - id: brightness
        type: bright_record
        repeat: expr
        repeat-expr: bright_count
        doc: '[CONFIRMED_LIVE] bright_count 6-byte brightness records'
      - id: colour_and_rest
        size-eos: true
        doc: '[INHERITED] colour sub-block + remainder; opaque. Carries the per-record speed byte.'
  bright_record:
    doc: 6-byte brightness record; the first two bytes are the relative-brightness interval (upper, lower).
    seq:
      - id: interval_upper
        type: u1
        doc: '[INFERRED] relative-brightness interval upper byte (round(pct x 2.55))'
      - id: interval_lower
        type: u1
        doc: '[INFERRED] relative-brightness interval lower byte (round(pct x 2.55))'
      - id: rest
        size: 4
        doc: '[INHERITED] remaining 4 record bytes; opaque'
