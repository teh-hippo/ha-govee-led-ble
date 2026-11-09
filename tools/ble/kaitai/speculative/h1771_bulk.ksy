meta:
  id: h1771_bulk
  title: H1771 candidate bulk observations
  endian: le
  imports:
    - ../govee_segment_page
    - h1771_status_reply
doc: |
  SPECULATIVE: H1771 bulk observations reconstructed from model behaviour, not
  confirmed by device traffic.  AC03 responses carry ordered length-delimited
  records split across fixed-size frames.  The 0x36 record's low three bits
  report master and two source flags.  Their physical source mapping remains
  unresolved.  Unknown records, bits and suffixes are retained.
seq:
  - id: header
    contents: [0xac]
  - id: index
    type: u1
  - id: body
    size: 17
    type:
      switch-on: index
      cases:
        0: first_frame
  - id: checksum
    type: u1
enums:
  domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x07: identity
    0x36: zone_enable
    0x41: power_on_behaviour
    0xa3: gradual
    0xa5: segments
  mode_code:
    0x04: scene
    0x0a: diy
    0x0d: static
    0x13: music
  power_on_state:
    0: previous
    1: "on"
    2: "off"
  identity_selector:
    0x10: main
    0x11: wireless
types:
  first_frame:
    seq:
      - id: frame_count
        type: u2
      - id: final_size
        type: u1
      - id: command
        contents: [0x03]
      - id: discriminator
        contents: [0x00]
      - id: payload
        size: 12
  query:
    seq:
      - id: header
        contents: [0xac, 0x03]
      - id: num_domains
        type: u1
      - id: domains
        type: u1
        enum: domain
        repeat: expr
        repeat-expr: num_domains
      - id: unknown_tail
        size: 16 - num_domains
      - id: checksum
        type: u1
  payload:
    seq:
      - id: records
        type: record
        repeat: eos
  record:
    seq:
      - id: domain
        type: u1
        enum: domain
      - id: len_body
        type: u1
      - id: body
        size: len_body
        type:
          switch-on: domain
          cases:
            'domain::power': power
            'domain::brightness': brightness
            'domain::colour_mode': mode_body
            'domain::identity': identity
            'domain::zone_enable': source_flags
            'domain::power_on_behaviour': power_on
            'domain::gradual': gradual
            'domain::segments': govee_segment_page(4, 4, false)
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
        size-eos: true
        type:
          switch-on: mode
          cases:
            'mode_code::scene': h1771_status_reply::scene_selector
            'mode_code::diy': h1771_status_reply::diy_selector
            'mode_code::static': static_mode
            'mode_code::music': h1771_status_reply::music
  static_mode:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
  identity:
    seq:
      - id: selector
        type: u1
        enum: identity_selector
      - id: detail
        size-eos: true
        type:
          switch-on: selector
          cases:
            'identity_selector::main': main_identity
            'identity_selector::wireless': wireless_identity
  main_identity:
    seq:
      - id: private_identifier
        size: 8
      - id: firmware
        type: version
      - id: hardware
        type: version
      - id: unknown_tail
        size-eos: true
  wireless_identity:
    seq:
      - id: private_identifier
        size: 6
      - id: firmware
        type: version
      - id: hardware
        type: version
      - id: unknown_tail
        size-eos: true
  version:
    seq:
      - id: major
        type: u1
      - id: minor
        type: u1
      - id: patch
        type: u1
  power_on:
    seq:
      - id: unknown_prefix
        type: u1
      - id: state
        type: u1
        enum: power_on_state
      - id: unknown_tail
        size-eos: true
  gradual:
    seq:
      - id: flag
        type: u1
      - id: unknown_tail
        size-eos: true
  source_flags:
    seq:
      - id: mask
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      master_enabled:
        value: (mask & 0x01) != 0
      source_0_enabled:
        value: (mask & 0x02) != 0
      source_1_enabled:
        value: (mask & 0x04) != 0
      unknown_mask:
        value: mask & 0xf8
  source_notification:
    seq:
      - id: header
        contents: [0xee, 0x30]
      - id: kind
        type: u1
      - id: flags
        type: source_flags
        size: 16
      - id: checksum
        type: u1
    instances:
      domain:
        value: '"zone_enable"'
      is_on:
        value: flags.master_enabled
      source_0_enabled:
        value: flags.source_0_enabled
      source_1_enabled:
        value: flags.source_1_enabled
