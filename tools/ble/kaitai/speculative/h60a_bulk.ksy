meta:
  id: h60a_bulk
  title: H60A1 and H60A6 bulk device observations
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H60A1 and H60A6 support for issue #402.  Compatibility
  hypothesis: AC03 reads return ordered, fixed-size response frames carrying
  a complete sequence of domain/length/value records.  The first response
  declares the frame count and final-frame payload length.  Single-frame
  responses carry at most twelve bytes; continuation frames carry seventeen.
  Mode, native H60A6 zone flags and power-on behaviour are independent
  observations, not proof of uploaded content or emitted light.  The AC30
  record has no master flag.  Unknown records, flag bits and suffixes remain
  opaque.  Capture qualification, other revisions and unsolicited response
  timing remain unresolved.  No timer or network records are interpreted.
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
    0x30: zone_enable
    0x41: power_on_behaviour
  mode:
    0x04: scene
    0x0a: diy
    0x0d: static_colour
    0x13: music
    0x15: static
  power_on_state:
    0: previous
    1: "on"
    2: "off"
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
      - id: domain_count
        type: u1
        valid:
          max: 16
      - id: domains
        type: u1
        enum: domain
        repeat: expr
        repeat-expr: domain_count
      - id: padding
        size: 16 - domain_count
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
      - id: length
        type: u1
      - id: body
        size: length
        type:
          switch-on: domain
          cases:
            'domain::power': power_body
            'domain::brightness': brightness_body
            'domain::colour_mode': mode_body
            'domain::zone_enable': zone_body
            'domain::power_on_behaviour': power_on_body
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode
      - id: detail
        size-eos: true
        type:
          switch-on: mode
          cases:
            'mode::scene': scene_body
            'mode::diy': diy_body
            'mode::static': static_body
            'mode::static_colour': colour_body
  scene_body:
    seq:
      - id: scene_id
        type: u2
      - id: unknown_tail
        size-eos: true
  diy_body:
    seq:
      - id: code
        type: u2
      - id: unknown_tail
        size-eos: true
  static_body:
    seq:
      - id: unknown_flag
        type: u1
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  zone_body:
    seq:
      - id: panel_flags
        type: u1
      - id: ring_flags
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      panel_enabled:
        value: (panel_flags & 1) != 0
      ring_enabled:
        value: (ring_flags & 1) != 0
  power_on_body:
    seq:
      - id: unknown_prefix
        type: u1
      - id: state
        type: u1
        enum: power_on_state
      - id: unknown_tail
        size-eos: true
