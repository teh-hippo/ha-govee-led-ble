meta:
  id: h6125_intermediate_status_reply
  title: Govee H6125 DreamColor RGB-only status replies
  endian: le
  imports:
    - h6125_status_reply
    - h6125_legacy_status_reply
    - h6102_status_reply
    - govee_rgb_segment_page
doc: |
  SPECULATIVE H6125, issue #117.
  Compatibility hypothesis: the intermediate DreamColor route keeps 0x0b
  RGB and A2 RGB-only pages, but uses 0x11 music and 16-bit scene/DIY selectors.
  Reachable application consumers establish the separate layouts. The app
  migration threshold alone is not a firmware compatibility guarantee.
  Unresolved assumptions: per-revision reply presence and unused bytes.
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
        'aa_domain::power': h6125_status_reply::power_body
        'aa_domain::brightness': h6125_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6125_status_reply::version_body
        'aa_domain::hw_version': h6125_status_reply::hw_version_body
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
        'aa_domain::segments': govee_rgb_segment_page(15)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa2: segments
    0xa3: multi_effect
  color_mode:
    0x04: scene
    0x0a: diy
    0x0b: static
    0x11: music
  scene_mode:
    0: sunrise
    1: sunset
    4: film
    5: date
    7: romantic
    8: blinking
    9: candle
    10: breathe
    15: snow
    16: energetic
    21: chase
    22: stream
    107: sweet
    110: halloween
    200: universe
    201: winter
    202: autumn
    203: deep_sea
    204: ripple
    205: meteor
    206: disco
    207: dream
    208: fireworks
    209: birthday
    210: spring
    211: valentines_day
    212: forest
    213: star
    214: lightning
    215: aurora
    216: fire
    217: starry_sky
    218: green_shade
    219: alarm
    220: ghost
    221: christmas
    222: new_year
    223: summer
    224: sport
    225: dance
    226: party
    227: waves
    228: meteor_shower
    229: game
    230: carnival
    231: mothers_day
    232: fathers_day
    233: night
    234: sleep
    235: morning
    236: afternoon
    237: study
    238: business
    239: reading
    240: excited
    241: happy
    242: enthusiastic
    243: profound
    244: mysterious
    245: quiet
    246: missing_you
    247: warm
    248: accumulation
    249: work
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
            'color_mode::static': h6125_legacy_status_reply::cm_static
            'color_mode::scene': h6125_status_reply::cm_scene
            'color_mode::diy': h6125_status_reply::cm_diy
            'color_mode::music': h6125_status_reply::cm_music
