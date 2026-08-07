meta:
  id: workshop_body
  title: Govee H617A reassembled Workshop layer-container body (A3 TYPE 0x02, decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame Workshop body (host concatenates each frame's
  bytes[2:19]; the frame checksum/terminator is transport, not modelled here).
  Workshop is identified by A3 TYPE 0x02 plus the activation 33 05 04 91 01 02.
  On-wire layout:
    01 <linecount> 02 <layer_count> [<record_len> <layer_record>]... <zero padding>
  The leading "01 <linecount> 02" is the generic build_a3_multi transport header
  ([0x01, chunk_count, type_byte]); linecount is the 17-byte chunk count and varies
  with body length (02 one layer, 04 two, 09 five). The reassembled body length is
  always a whole number of 17-byte chunks, so linecount == len / 17.
  Each layer is a length-prefixed record; the remainder after the records is
  transport zero padding to the 17-byte A3 chunk boundary, outside the records.
  Re-verified against captured Workshop bodies (Christmas 5-layer, the select-type
  matrix, colour-family, brightness, movement and priority differentials); captures
  are ground truth. This is a DECODE-ONLY structural spec and models no write side.

  Activation (, live): a Workshop effect is applied by uploading this body
  then writing 33 05 04 91 01 02 -- colour-mode 0x04 with the u2le id 0x0191 (401) and
  a trailing 0x02. The id 401 is FIXED for every Workshop item: a newly crafted
  one-layer effect and the pre-existing five-layer Christmas both activate with it, and
  401 is absent from the frozen effect-library catalogue. Catalogue scenes instead use
  33 05 04 <catalogue_id> 00, so the trailing byte discriminates catalogue (0x00) from
  Workshop (0x02). Because 401 identifies no particular effect and the body is never
  read back (the aa a3 query returns an empty body), the device cannot report WHICH
  Workshop effect is running. Applying a saved item re-uploads the whole body every
  time; nothing is stored device-side by reference.

  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
seq:
  - id: header
    type: govee_common::a3_header
    doc: >
      shared A3 body header 01 <linecount>. linecount is the 17-byte
      data-chunk count and equals len/17 (02 for one layer, 03/04 for larger, 09 for
      the five-layer Christmas body); the body is zero-padded to whole 17-byte chunks.
  - id: a3_type
    contents: [0x02]
    doc: >
      A3 TYPE 0x02; Workshop is always type 0x02 (raw). This is the
      SAME positional byte that scene_body.ksy calls `scene_type` (reassembled-body
      offset 2); the two specs name one byte differently. It is NOT the activation
      frame's scene-type byte in command_write.ksy, which is independent -- an
      Effects Lab scene edit carries A3 type 0x02 here yet activates with 0x00.
  - id: layer_count
    type: u1
    doc: 'number of length-prefixed layer records that follow (1/2/5 seen).'
  - id: layers
    type: layer_record
    repeat: expr
    repeat-expr: layer_count
    doc: 'layer_count length-prefixed records, emitted in creation order.'
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: 'transport zero padding to the 17-byte A3 chunk boundary; grammar-enforced all-zero.'
types:
  layer_record:
    doc: |
      One Workshop layer: a 1-byte length then that many record bytes. The record
      length grows only with the colour count M (record_len == 23 + 3*M), confirmed
      byte-exact for M = 1, 2 and 3, and extended  to M = 4 and M = 5 by the
      Effects Lab bodies (record_len 35 and 38). The rule was also used as an advance
      PREDICTION: a hand-crafted two-colour layer was predicted to emit record_len 29
      before it was applied, and the capture matched, along with r1 = 0x00 (whole
      strip), r2 = 0x01, r4 = 0x0f and the chosen red/blue palette.
    seq:
      - id: record_len
        type: u1
        doc: 'r0: number of record bytes that follow this length byte (0x1a M=1, 0x1d M=2, 0x20 M=3).'
      - id: body
        type: govee_common::effect_layer
        size: record_len
        doc: 'the record body, constrained to record_len bytes.'
