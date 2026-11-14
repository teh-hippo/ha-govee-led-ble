meta:
  id: h1771_status_reply
  title: H1771 candidate ordinary status replies
  endian: le
  imports:
    - ../govee_segment_page
    - h1771_music_body
doc: |
  SPECULATIVE: H1771 reply layouts are only partially confirmed by device
  traffic.  Hardware 3.08.01 / firmware 1.00.09 reports 2200 K with static
  selector 0x15, flag 0 and big-endian Kelvin.  The 0x0d route remains a
  separate candidate selector.  Static mode reports a flag and Kelvin, while
  segment pages report rendered RGB and relative brightness.  These are
  independent observations and do not prove a per-source Kelvin value.
  Unknown suffixes are retained.
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
        'status_domain::power': power
        'status_domain::brightness': brightness
        'status_domain::colour_mode': mode_body
        'status_domain::segments': govee_segment_page(4, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0xa5: segments
  mode_code:
    0x04: scene
    0x0a: diy
    0x0d: static
    0x13: music
    0x15: static_colour
types:
  power:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_code
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_code::scene': scene_selector
            'mode_code::diy': diy_selector
            'mode_code::static': colour
            'mode_code::static_colour': colour
            'mode_code::music': music
  scene_selector:
    seq:
      - id: scene_id
        type: u2
      - id: unknown_tail
        size-eos: true
  diy_selector:
    seq:
      - id: code
        type: u2
      - id: unknown_tail
        size-eos: true
  colour:
    seq:
      - id: flag
        type: u1
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  music:
    seq:
      - id: mode
        type: u1
        enum: h1771_music_body::music_mode
      - id: sensitivity
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: false
