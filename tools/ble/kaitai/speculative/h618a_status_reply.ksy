meta:
  id: h618a_status_reply
  title: Govee H618A candidate status replies
  endian: le
  imports:
    - h619a_status_reply
    - ../govee_segment_page
doc: |
  SPECULATIVE H618A status contract for Pacts 2/1 and 3/1.
  Fifteen logical positions use three-record A5 brightness/RGB pages at
  firmware 1.06.00 and hardware 1.00.02 or newer. Earlier versions use A2
  RGB-only pages independently of the compatible masked colour writes.
  Static mode carries a flag and big-endian Kelvin, not independent RGB.
  No gradual control or dedicated white emitter is established.
  Unknown bytes and physical reply availability remain unqualified.
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
        'aa_domain::segments': govee_segment_page(15, 3, false)
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
