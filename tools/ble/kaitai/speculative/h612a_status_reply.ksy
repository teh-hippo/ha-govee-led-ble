meta:
  id: h612a_status_reply
  title: Govee H612A status-reply envelope
  endian: le
  imports:
    - ../govee_common
    - ../govee_segment_page
    - ../govee_shared
    - ../status_reply
doc: |
  SPECULATIVE: H612A replies for power, percentage brightness, mode, identity,
  Pact, physical IC count, power-on behaviour, gradual state and colour groups.
  Colour observations use four records per page.  The physical strip has up to
  20 ICs and exposes 10 logical sections.  No complete owner capture is
  available yet; unknown bytes remain opaque.
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
        'aa_domain::power': power_body
        'aa_domain::brightness': brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::physical_ic_count': physical_ic_count_body
        'aa_domain::power_on_behaviour': power_on_body
        'aa_domain::pact': pact_body
        'aa_domain::gradual': gradual_body
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
    0x40: physical_ic_count
    0x41: power_on_behaviour
    0xa3: gradual
    0xa5: segments
    0xef: pact
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
  power_on_state:
    0: previous
    1: "on"
    2: "off"
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
        valid:
          max: 100
      - id: unknown_tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  hw_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  physical_ic_count_body:
    seq:
      - id: count
        type: s2be
      - id: unknown_tail
        size-eos: true
  power_on_body:
    seq:
      - id: open_flag
        type: u1
        valid:
          any-of: [0, 1]
      - id: state
        type: u1
        enum: power_on_state
      - id: unknown_tail
        size-eos: true
  pact_body:
    seq:
      - id: pact_type
        type: u2be
      - id: pact_code
        type: u1
      - id: unknown_tail
        size-eos: true
  gradual_body:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
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
            'color_mode::static': status_reply::cm_static
            'color_mode::scene': scene_selector
            'color_mode::diy': govee_common::diy_selector
            'color_mode::music': govee_common::music_selector
  scene_selector:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
