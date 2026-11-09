meta:
  id: h1771_effect_upload
  title: H1771 candidate native DIY upload
  endian: le
  imports:
    - h1771_diy_body
doc: |
  SPECULATIVE: H1771 multipart upload reconstructed from model behaviour, not
  confirmed by device traffic.  Native DIY and DIY-based scenes carry a
  length-delimited two-section body and are activated separately.  Padding
  and unqualified suffixes remain opaque.
seq:
  - id: marker
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: upload_kind
  - id: body
    size-eos: true
    type:
      switch-on: kind
      cases:
        'upload_kind::native_diy': h1771_diy_body
enums:
  upload_kind:
    0x01: rgb_scene
    0x02: layered_scene
    0x41: music
    0x58: native_diy
