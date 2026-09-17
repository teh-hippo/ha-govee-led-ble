meta:
  id: h66a0_video_status
  endian: le
  imports:
    - h66a0_video_command
doc: |
  SPECULATIVE H66A0 minimal status fixture for issues #257 and #297.
  Contributor round2 reports aa 05 video replies share the command body.
  Only power, brightness and video read domains are represented. Independent
  captures and firmware coverage remain unresolved; no runtime model enabled.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: read_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'read_domain::power': power_body
        'read_domain::brightness': brightness_body
        'read_domain::colour_mode': mode_body
  - id: checksum
    type: u1
enums:
  read_domain:
    1: power
    4: brightness
    5: colour_mode
  mode_sel:
    0: video
types:
  power_body:
    seq:
      - id: is_on
        type: u1
  brightness_body:
    seq:
      - id: percent
        type: u1
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_sel
      - id: detail
        type: h66a0_video_command::video_body
        size: 16
