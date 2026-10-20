meta:
  id: h6125_modern_status_reply
  title: Govee H6125 pact-10 status replies
  endian: le
  imports:
    - h6125_status_reply
    - h6102_status_reply
    - ../govee_segment_page
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: the pact-10 DreamColor route uses percentage
  brightness, submode 0x13 music and five three-record brightness/RGB pages.
  Reachable application consumers share these fields with the H6102 modern
  route. This does not establish hardware qualification or zero-valued tails.
  Unresolved assumptions: firmware-specific reply presence and unused bytes.
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
        'aa_domain::power': h6125_status_reply::power_body
        'aa_domain::brightness': h6102_status_reply::brightness_body
        'aa_domain::colormode': h6102_status_reply::colormode_body
        'aa_domain::fw_version': h6125_status_reply::version_body
        'aa_domain::hw_version': h6125_status_reply::hw_version_body
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
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
    0xa3: multi_effect
    0xa5: segments
