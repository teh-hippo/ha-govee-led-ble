meta:
  id: h618a_pact3_status_reply
  title: Govee H618A Pact 3 status replies
  endian: le
  imports:
    - h619a_status_reply
    - ../govee_segment_page
doc: |
  SPECULATIVE H618A status contract for Pact 3/1 hardware 3.x.
  Fifteen logical positions use four-record A5 brightness/RGB pages.
  Static mode, power, brightness and identity share the H619A reply shapes.
  Unknown bytes and reply availability on other Pact 3 revisions remain unqualified.
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
        'aa_domain::power': h619a_status_reply::power_body
        'aa_domain::brightness': h619a_status_reply::brightness_body
        'aa_domain::colormode': h619a_status_reply::colormode_body
        'aa_domain::fw_version': h619a_status_reply::version_body
        'aa_domain::hw_version': h619a_status_reply::hw_version_body
        'aa_domain::segments': govee_segment_page(15, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
