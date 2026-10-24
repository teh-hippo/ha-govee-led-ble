meta:
  id: h61f5_status_reply
  title: Govee H61F5 speculative AA status envelope (decode-only)
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_shared
doc: |
  SPECULATIVE H61F5, issue #392.
  Compatibility hypothesis: the H61F5 Strip Light 2 Pro (goodsType 261, Pact 3/1)
  replies with 20-byte XOR-checksummed AA frames carrying power, percentage
  brightness, active colour mode, firmware and hardware version strings,
  subordinate version strings (AA 20 / AA 21), physical IC count (AA 40),
  gradual-change boolean register (AA A3), and up to ten logical segments across
  three four-record AA A5 pages (4+4+2 uncut; narrowed by AA 40 on cut strips).
  Static colour replies (0x15) carry the gradual flag and big-endian Kelvin;
  scene (0x04) and DIY (0x0a) replies carry little-endian selectors; music
  replies (0x13) carry the mode ID, sensitivity, and selector settings for
  legacy modes.
  Issue #429 reports zero in the Kelvin field after both whole-device and partial
  native-Kelvin writes.  It is not a Kelvin measurement or proof of RGB intent.
  Segment pages may temporarily be black before settling with unchanged brightness.
  Unresolved assumptions: exact firmware-specific reply presence and all trailing
  bytes in status and segment replies.  Trailing bytes remain opaque rather than
  validated as zeroes.
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
        'aa_domain::subordinate_20': version_body
        'aa_domain::subordinate_21': version_body
        'aa_domain::physical_ic_count': physical_ic_count_body
        'aa_domain::multi_effect': multi_effect_body
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
    0xa3: multi_effect
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
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
    0x84: splash
    0x85: spring
    0x8b: meteor
    0x92: ripple
    0xa3: orbit
types:
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
      - id: unknown_tail
        size-eos: true
  physical_ic_count_body:
    seq:
      - id: count
        type: s2be
      - id: unknown_tail
        size-eos: true
  multi_effect_body:
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
            'color_mode::static': cm_static
            'color_mode::scene': cm_scene
            'color_mode::diy': cm_diy
            'color_mode::music': cm_music
  cm_static:
    seq:
      - id: sub
        doc: Gradual flag in static-colour status replies; not the write operation byte.
        type: u1
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  cm_scene:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  cm_diy:
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
  cm_music:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
        if: is_legacy
      - id: has_fixed_colour
        type: u1
        if: is_legacy
      - id: rgb
        type: govee_shared::rgb
        if: is_legacy
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: >-
          mode_id == music_mode::rhythm or mode_id == music_mode::spectrum or
          mode_id == music_mode::energetic or mode_id == music_mode::rolling
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
