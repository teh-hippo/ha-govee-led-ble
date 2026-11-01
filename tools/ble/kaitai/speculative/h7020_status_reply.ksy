meta:
  id: h7020_status_reply
  title: H7020 candidate complete status root
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - ../govee_segment_page
    - ../status_reply
doc: |
  H7020. AA0F is configured string count, not
  detected attachment or IC count. A5 carries three brightness/RGB records per
  page. The coordinator additionally limits pages to the confirmed layout.
  AA05 reports mode and one Kelvin value, not per-bulb white intent, uploaded
  effect bodies, speed or Rhythm response. Legacy music's selector-4 extra byte
  does not establish the authored selector-3 response parameter.
  Unresolved assumptions: no exact-model captures qualify these full replies,
  unused suffixes, ten-page completion or concurrent count-change behaviour.
  Unknown bytes are preserved; no zero-padding assumption is imposed.
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
        'aa_domain::configured_strings': configured_strings_body
        'aa_domain::power_off_memory': boolean_body
        'aa_domain::segments': govee_segment_page(30, 3, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x0f: configured_strings
    0x41: power_off_memory
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
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
  configured_strings_body:
    seq:
      - id: count
        type: u1
        valid:
          any-of: [1, 2]
      - id: unknown_tail
        size-eos: true
  boolean_body:
    seq:
      - id: flag
        type: u1
        valid:
          any-of: [0, 1]
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
            'color_mode::scene': scene_body
            'color_mode::diy': govee_common::diy_selector
            'color_mode::music': music_body
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  music_body:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: unknown_selector_parameter
        type: u1
        if: mode_id == music_mode::spectrum
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
