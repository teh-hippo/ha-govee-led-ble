meta:
  id: h705a_status_reply
  title: H705A candidate status envelope
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_shared
    - h6102_status_reply
    - h705a_music_write
doc: |
  SPECULATIVE: H705A power, percentage brightness, identity, physical IC count,
  active mode and four-record A5 readback share the ordinary AA envelope.
  The current status route reads the gradual flag and big-endian Kelvin,
  obtaining colours from A5. An older route instead interprets the same mode
  as operation, RGB and Kelvin; its revision boundary is not established.
  That alternative is documented separately and is not inferred by guessing
  whether arbitrary RGB bytes resemble a valid temperature.
  Native scenes and DIY report only their selectors, not retained upload bodies.
  Music readback reports selector and sensitivity; suffixes remain opaque.
  Segment cardinality is bounded by the product capacity and narrowed by the
  currently observed installation in the shared runtime.
  Physical operation and firmware-specific response presence await owner tests.
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
        'aa_domain::power': h6102_status_reply::power_body
        'aa_domain::brightness': h6102_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': h6102_status_reply::hw_version_body
        'aa_domain::physical_ic_count': physical_ic_count_body
        'aa_domain::multi_effect': boolean_body
        'aa_domain::segments': govee_segment_page(27, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x40: physical_ic_count
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
  physical_ic_count_body:
    seq:
      - id: count
        type: u2be
      - id: unknown_tail
        size-eos: true
  boolean_body:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
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
            'color_mode::static': h6102_status_reply::cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::music': h705a_music_write::music_selector
  legacy_cm_static:
    seq:
      - id: sub
        type: u1
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
