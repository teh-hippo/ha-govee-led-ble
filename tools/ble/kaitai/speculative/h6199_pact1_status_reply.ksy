meta:
  id: h6199_pact1_status_reply
  title: Govee H6199 Pact 1 status reply
  endian: le
  imports:
    - ../h6199_status_reply
    - h6199_pact1_wire_write
    - govee_rgb_segment_page
doc: |
  SPECULATIVE: H6199 Pact 1/1 reports scaled brightness, RGB-only
  segment pages and a legacy mode selector.  Static mode detail does not
  establish RGB or an exact Kelvin observation.  Retain unread fields as bytes.
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
        'status_domain::power': h6199_status_reply::power_body
        'status_domain::brightness': h6199_status_reply::brightness_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::firmware': h6199_status_reply::version_body
        'status_domain::hardware': h6199_status_reply::hardware_version_body
        'status_domain::legacy_segments': govee_rgb_segment_page(15, 4)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0xa2: legacy_segments
  mode_sel:
    0x04: scene
    0x0b: static_colour
    0x0c: music
types:
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_sel::scene': h6199_status_reply::scene_state
            'mode_sel::music': h6199_pact1_wire_write::music_body
