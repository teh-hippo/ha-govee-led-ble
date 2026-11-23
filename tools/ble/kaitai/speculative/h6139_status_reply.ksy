meta:
  id: h6139_status_reply
  title: Govee H6139 whole-strip status
  endian: be
  imports:
    - h6181_status_reply
    - h6159_status_reply
    - h6139_wire_write
doc: |
  SPECULATIVE H6139 status, awaiting recorded device traffic.
  AA01 reports power, AA04 brightness, AA06 ASCII firmware and AA07/03
  ASCII hardware. AA05/01 queries mode. Original mode02 carries RGB,
  a temperature flag and companion RGB; mode0D carries Kelvin BE16.
  Original music03 is followed by fixed-colour flag and sensitivity.
  Music0E carries dynamic0/soft1 or palettes48/49; later13 additionally
  carries a style byte. Palette parameters are not independently read.
  Brightness scaling belongs to the qualified controller profile.
  Scene04 and DIY0A carry LE16 selectors. Unqualified tails stay opaque.
  Decode-only AA0A, AA11 and AA12 schedule replies retain the write-body
  field order. State and repeat bytes remain uninterpreted.
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
        'aa_domain::power': h6181_status_reply::power_body
        'aa_domain::brightness': h6181_status_reply::brightness_body
        'aa_domain::colour_mode': h6159_status_reply::colour_mode_body
        'aa_domain::firmware': h6181_status_reply::version_body
        'aa_domain::hardware': h6181_status_reply::hardware_body
        'aa_domain::timer': h6139_wire_write::timer_body
        'aa_domain::sleep': h6139_wire_write::sleep_body
        'aa_domain::wake': h6139_wire_write::wake_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x0a: timer
    0x11: sleep
    0x12: wake
