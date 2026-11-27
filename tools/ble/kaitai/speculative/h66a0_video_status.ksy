meta:
  id: h66a0_video_status
  endian: le
  imports:
    - h66a0_video_command
doc: |
  SPECULATIVE H66A0 minimal status layout.  Closed owner-confirmation issue #450
  (https://github.com/teh-hippo/ha-govee-led-ble/issues/450) records standalone
  Video Movie as visibly working on Supported H66A0 HW 3.07.01/FW 1.00.24.
  It separately records Game/Movie switching and readback in DreamView
  sync-centre mode, which is a distinct control path; standalone Game readback
  remains unconfirmed.  The owner evidence qualifies those visible operations,
  not every byte here.  Contributor round2 reports aa 05 video replies share
  the command body; only power, brightness and video read domains are
  represented here.  Other byte meanings, reply variants, wire values and
  other hardware or firmware revisions remain unqualified.
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
