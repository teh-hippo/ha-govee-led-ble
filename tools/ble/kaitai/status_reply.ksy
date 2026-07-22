meta:
  id: status_reply
  title: Govee H617A "aa" status-reply envelope (decode-only)
  endian: le
doc: |
  Light -> phone status notification, 20 bytes: aa <domain> <17-byte body> <xor>.
  byte[19] is the XOR of bytes[0..18]; opaque here and validated host-side.
  One envelope for the whole aa readback family; per-domain bodies below.
  Re-verified against captured replies; captures are ground truth.
  Colour-mode (domain 0x05) is currently specified in colormode_readback.ksy and
  will be composed in here in a follow-on rather than duplicated.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: aa_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'aa_domain::power': power_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::segments': segments_body
        'aa_domain::timer': timer_body
    doc: bytes 2..18, interpreted per domain (unmatched domains fall back to raw)
  - id: checksum
    type: u1
    doc: raw XOR of bytes[0..18]; opaque, host-validated
enums:
  aa_domain:
    0x01: power
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x23: timer
    0xa5: segments
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        doc: raw power state, 0x00 off / 0x01 on
  version_body:
    doc: firmware version, ASCII, NUL-terminated (e.g. "3.02.24")
    seq:
      - id: text
        type: strz
        encoding: ASCII
  hw_version_body:
    doc: hardware version; a 0x03 prefix then ASCII NUL-terminated (e.g. "3.01.01")
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
  segments_body:
    doc: group id then three segments of <brightness> <R> <G> <B> (aa a5 read-back)
    seq:
      - id: group
        type: u1
        doc: raw group id (01..05)
      - id: segments
        type: segment
        repeat: expr
        repeat-expr: 3
  segment:
    seq:
      - id: brightness
        type: u1
      - id: r
        type: u1
      - id: g
        type: u1
      - id: b
        type: u1
  timer_body:
    doc: ff-prefixed 4-slot schedule table; slot internals INHERITED (decoded in a later increment)
    seq:
      - id: marker
        contents: [0xff]
      - id: slots_raw
        size-eos: true
        doc: opaque 4-slot region (INHERITED, not yet field-decoded)
