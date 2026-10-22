meta:
  id: h7025_status_reply
  title: Govee H7025 basic, segment and music status
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_shared
    - h6102_status_reply
doc: |
  SPECULATIVE H7025, issue #148.
  In Android 7.6.01, H7025 uses the shared power, brightness, and identity
  status layouts, dispatches AA05 mode 15 to static colour, 04 to scenes, 0A to
  DIY, and 13 to music state, and reads A5 segment pages of four brightness/RGB
  records across fifteen logical positions.  Music replies carry only ID and
  sensitivity for companion-backed modes and flags plus one RGB triple for
  Rhythm.
  Compatibility hypothesis: these basic fields share the modern AA envelope.
  Shared H617A command_write/status_query codecs provide power, percent
  brightness, AA0501, identity queries, A5 segment queries, and two-byte-mask
  330515 colour/Kelvin/brightness writes; H7025 has fifteen bulbs and a
  2700..6500 Kelvin range.  Goods type 296 uses command version 0 and Kelvin
  type 1, emitting RGB with a two-byte mask and direct white RGB plus
  table-derived companion RGB for Kelvin.
  Common payload imports do not inherit H6102's product capabilities.
  Unknown modes, suffixes, and other domains stay opaque.  No full palette
  readback is claimed by this candidate.
  Unresolved: reporter hardware/firmware revisions, identity response encoding,
  response presence, RGB/Kelvin rendering, and physical BLE qualification.
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
        'aa_domain::segments': govee_segment_page(15, 4, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
  music_mode:
    0x03: rhythm
    0x8e: sway
    0x59: flow
    0x98: star
    0x8f: twinkle
    0x48: hopping
    0x5a: rolling
    0x37: day_and_night
    0x34: piano_keys
    0x5d: separation
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
            'color_mode::static': h6102_status_reply::cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::music': cm_music
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
        if: is_legacy and has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: mode_id == music_mode::rhythm
