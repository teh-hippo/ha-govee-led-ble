meta:
  id: synthetic_static_status_reply
  title: Synthetic optional static colour status (fixture only)
  endian: le
  imports:
    - /govee_segment_page
    - /status_reply
doc: |
  SPECULATIVE test-only layout for issue #286, not a device protocol claim.
  H7001 is a synthetic exact profile, not a supported product. Flags, RGB and
  Kelvin fields here are invented solely to exercise optional observation;
  no physical device is assumed to use these bytes. Segment pages reuse the
  existing three-slot layout; scene selectors reuse the evidenced H617A layout
  for transition tests. This root is never enabled in runtime builds.
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
        'status_domain::colormode': colour_body
        'status_domain::segments': govee_segment_page(15, 3, true)
  - id: checksum
    type: u1
types:
  colour_body:
    seq:
      - id: mode
        type: u1
        enum: colour_mode
      - id: mode_body
        type:
          switch-on: mode
          cases:
            'colour_mode::static': static_body
            'colour_mode::scene': status_reply::cm_scene
  static_body:
    instances:
      sub:
        value: 1
    seq:
      - id: flags
        type: u1
      - id: rgb
        type: rgb_value
        if: (flags & 1) != 0
      - id: kelvin
        type: u2
        if: (flags & 2) != 0
      - id: unknown
        size-eos: true
  rgb_value:
    seq:
      - id: red
        type: u1
      - id: green
        type: u1
      - id: blue
        type: u1
enums:
  status_domain:
    0x05: colormode
    0xa5: segments
  colour_mode:
    0x15: static
    0x04: scene
