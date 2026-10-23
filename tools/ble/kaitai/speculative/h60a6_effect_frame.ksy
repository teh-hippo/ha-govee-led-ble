meta:
  id: h60a6_effect_frame
  title: H60A6 native DIY and paint upload envelopes
  endian: le
  imports:
    - h60a6_diy_body
doc: |
  SPECULATIVE H60A6 support for issue #402.  Compatibility hypothesis:
  native paint bodies use A4, a sixteen-bit frame index/count and subtype 58.
  Frames have a trailing XOR byte.  The start frame contains marker 01,
  count and subtype; the final frame has index FFFF.  Single-data-frame
  uploads include an empty four-byte terminator.  Final frames are not
  padded.  MTU negotiation, acknowledgement timing, other revisions and
  hardware rendering require capture qualification.  A3 DIY uses the same
  subtype but a different body family and framing.  Its reassembled envelope
  embeds the length-bounded DIY body separately from transport fill.
seq:
  - id: header
    contents: [0xa4]
  - id: index
    type: u2
  - id: body
    size: _io.size - 4
    type:
      switch-on: index
      cases:
        0: start_body
  - id: checksum
    type: u1
enums:
  subtype:
    0x58: native_effect
types:
  a3_envelope:
    seq:
      - id: marker
        contents: [0x01]
      - id: frame_count
        type: u1
      - id: subtype
        type: u1
        enum: subtype
        valid: subtype::native_effect
      - id: body
        type: h60a6_diy_body
      - id: padding
        size-eos: true
  start_body:
    seq:
      - id: marker
        contents: [0x01]
      - id: frame_count
        type: u2
      - id: subtype
        type: u1
        enum: subtype
      - id: payload
        size-eos: true
  a3_body:
    seq:
      - id: subtype
        type: u1
        enum: subtype
      - id: payload
        size-eos: true
