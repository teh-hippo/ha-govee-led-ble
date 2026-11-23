meta:
  id: h6053_status_reply
  title: Govee H6053 status replies
  endian: le
  imports:
    - ../govee_shared
    - ../govee_segment_page
    - h6046_status_reply
    - h6046_command_write
    - h6053_wire_write
doc: |
  SPECULATIVE: reconstructed H6053 replies, without recorded device traffic.
  Pact 1/1 brightness carries a 20..254 register; Pact 2/1 carries percent.
  Legacy static mode reports each bar's RGB and big-endian Kelvin directly.
  Modern static mode reports independent bar Kelvin; twelve rendered colours
  and relative levels are read in three pages of four records.
  Scene and DIY selectors do not confirm uploaded content or rendering.
  Unknown suffixes are retained. Reply timing, version envelope variants,
  acknowledgements and physical white rendering require owner verification.
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
        'status_domain::power': h6046_status_reply::power_body
        'status_domain::brightness': h6046_status_reply::brightness_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::firmware': h6046_status_reply::version_body
        'status_domain::hardware': h6046_status_reply::hardware_version_body
        'status_domain::pact': pact_body
        'status_domain::bar_enable': h6046_status_reply::bar_enable_body
        'status_domain::segments': govee_segment_page(12, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x33: bar_enable
    0xa5: segments
    0xef: pact
  mode_sel:
    0x04: scene
    0x0a: diy
    0x0c: legacy_music
    0x0d: legacy_colour
    0x13: music
    0x15: static_colour
types:
  pact_body:
    seq:
      - id: pact_type
        type: u2be
      - id: pact_code
        type: u1
      - id: unknown_tail
        size-eos: true
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_sel::legacy_colour': legacy_colour
            'mode_sel::static_colour': h6046_status_reply::static_detail
            'mode_sel::scene': h6046_status_reply::scene_detail
            'mode_sel::diy': h6046_status_reply::diy_detail
            'mode_sel::legacy_music': legacy_music
            'mode_sel::music': music_detail
  legacy_music:
    doc: RX contains both RGB triples, not the TX target mask.
    seq:
      - id: mode
        type: u1
        enum: h6053_wire_write::music_mode
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
        if: mode == h6053_wire_write::music_mode::rhythm
      - id: has_fixed_colour
        type: u1
        if: is_base
      - id: left_colour
        type: govee_shared::rgb
        if: is_base
      - id: right_colour
        type: govee_shared::rgb
        if: is_base
      - id: unknown_tail
        size-eos: true
    instances:
      is_base:
        value: |
          mode == h6053_wire_write::music_mode::energetic or
          mode == h6053_wire_write::music_mode::rhythm or
          mode == h6053_wire_write::music_mode::impact or
          mode == h6053_wire_write::music_mode::spray
  music_detail:
    doc: |
      Pact 2/1 RX. Energetic selector 5 has conflicting observed-layout
      descriptions: one includes a style byte and another does not.
      Only its mode and sensitivity are interpreted until hardware qualifies
      the colour fields. Rhythm selector 3 unambiguously carries style.
    seq:
      - id: mode
        type: u1
        enum: h6046_command_write::music_mode
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
        if: mode == h6046_command_write::music_mode::rhythm
      - id: has_fixed_colour
        type: u1
        if: is_base
      - id: left_colour
        type: govee_shared::rgb
        if: is_base
      - id: right_colour
        type: govee_shared::rgb
        if: is_base
      - id: unknown_tail
        size-eos: true
    instances:
      is_base:
        value: |
          mode == h6046_command_write::music_mode::rhythm or
          mode == h6046_command_write::music_mode::impact or
          mode == h6046_command_write::music_mode::spray
  legacy_colour:
    seq:
      - id: sources
        type: source_colour
        repeat: expr
        repeat-expr: 2
      - id: unknown_tail
        size-eos: true
  source_colour:
    seq:
      - id: colour
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
