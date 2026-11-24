meta:
  id: h619a_legacy_status_reply
  title: Govee H619A candidate RGB-only status replies
  endian: le
  imports:
    - h619a_status_reply
    - govee_rgb_segment_page
doc: |
  SPECULATIVE H619A status before firmware 1.06.00 and hardware 1.00.02
  are both qualified. Four RGB-only records per A2 page cover ten logical
  positions. Relative brightness writes remain independently supported;
  these pages cannot confirm their values.
  Mode, power, brightness, gradual and identity share the later reply
  structures. Opaque suffixes are retained without invented constraints.
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
        'aa_domain::multi_effect': h619a_status_reply::multi_effect_body
        'aa_domain::segments': govee_rgb_segment_page(10, 4)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa2: segments
    0xa3: multi_effect
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
