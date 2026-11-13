meta:
  id: h60b2_effect_upload
  title: H60B2 candidate native DIY upload envelope
  endian: le
  imports:
    - h60b2_diy_body
doc: |
  SPECULATIVE: Multipart envelope for native family 803. Framing is shared
  with ordinary A3 uploads; the length-delimited native body is independent
  of RGB/RGBIC scene bodies. Activation follows the positive upload result.
seq:
  - id: marker
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: upload_kind
  - id: body
    type: h60b2_diy_body
enums:
  upload_kind:
    0x58: native_diy
