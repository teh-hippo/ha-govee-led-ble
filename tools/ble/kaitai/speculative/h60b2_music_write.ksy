meta:
  id: h60b2_music_write
  title: H60B2 candidate onboard music selector
  endian: le
  imports:
    - h60b2_music_body
doc: |
  SPECULATIVE: Onboard music activation follows its A3 companion upload.
  The ordinary selector carries only the exact-product mode and sensitivity.
  Unknown suffixes are retained; this does not establish hardware confirmation.
seq:
  - id: header
    contents: [0x33, 0x05, 0x13]
  - id: selector
    size: 16
    type: music_selector
  - id: checksum
    type: u1
types:
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: h60b2_music_body::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: false
