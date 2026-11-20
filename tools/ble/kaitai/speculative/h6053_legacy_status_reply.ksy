meta:
  id: h6053_legacy_status_reply
  title: Govee H6053 legacy inline status replies
  endian: le
  imports:
    - h6046_status_reply
    - h6053_status_reply
doc: |
  SPECULATIVE: reconstructed legacy H6053 status, without recorded traffic.
  AA05 reports the two bars' colours and Kelvin directly. Legacy geometry
  does not establish support for modern A5 twelve-position pages.
  Pact-selected music and brightness remain independent of static geometry.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: status_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'status_domain::power': h6046_status_reply::power_body
        'status_domain::brightness': h6046_status_reply::brightness_body
        'status_domain::colour_mode': h6053_status_reply::colour_mode_body
        'status_domain::firmware': h6046_status_reply::version_body
        'status_domain::hardware': h6046_status_reply::hardware_version_body
        'status_domain::bar_enable': h6046_status_reply::bar_enable_body
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x33: bar_enable
