meta:
  id: h1ab2_status_reply
  title: Govee H1AB2 AA status envelope
  endian: le
  imports:
    - ../govee_segment_page
    - h1ab2_music_write
    - h1a42_status_reply
    - h6097_control
doc: |
  SPECULATIVE: H1AB2 uses 20-byte XOR-checksummed AA replies for power,
  brightness, mode, firmware/hardware, subordinate versions, installed IC
  count, gradual and segment colours. Ten logical segments use four records
  per A5 page. The logical count is min(installed IC count, 10), not ICs/5.
  Static mode carries gradual and big-endian Kelvin; segment records carry
  rendered RGB and relative brightness, not per-segment native Kelvin.
  Exact reply availability, zero-Kelvin semantics and opaque tails remain
  unconfirmed for individual hardware and firmware revisions.
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
        'aa_domain::power': h1a42_status_reply::power_body
        'aa_domain::brightness': h1a42_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h1a42_status_reply::version_body
        'aa_domain::hw_version': h1a42_status_reply::hw_version_body
        'aa_domain::subordinate_20': h1a42_status_reply::version_body
        'aa_domain::subordinate_21': h1a42_status_reply::version_body
        'aa_domain::physical_ic_count': h1a42_status_reply::physical_ic_count_body
        'aa_domain::power_on_behaviour': h6097_control::power_on_state
        'aa_domain::multi_effect': h1a42_status_reply::multi_effect_body
        'aa_domain::segments': govee_segment_page(10, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x20: subordinate_20
    0x21: subordinate_21
    0x40: physical_ic_count
    0x41: power_on_behaviour
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
  colormode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: mode_body
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::static': h1a42_status_reply::cm_static
            'color_mode::scene': h1a42_status_reply::cm_scene
            'color_mode::diy': h1a42_status_reply::cm_diy
            'color_mode::music': h1ab2_music_write::music_selector
