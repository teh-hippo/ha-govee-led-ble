meta:
  id: h6102_intermediate_status_reply
  title: Govee H6102 Pact 1 intermediate AA status replies
  endian: le
  imports:
    - h6102_status_reply
    - h6102_legacy_status_reply
    - ../govee_shared
doc: |
  H6102.
  The Pact 1 intermediate route keeps legacy static mode 02, with 0x11 music
  and the shared 16-bit scene/DIY selectors. Unknown tails stay opaque.
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
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
  color_mode:
    0x02: static
    0x04: scene
    0x0a: diy
    0x11: music
  music_mode:
    0x10: energetic
    0x11: rhythm
    0x12: spectrum
    0x13: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
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
            'color_mode::static': h6102_legacy_status_reply::cm_static
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
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'music_mode::rhythm': rhythm_settings
            'music_mode::spectrum': colour_settings
            'music_mode::rolling': colour_settings
            _: opaque_settings
    instances:
      is_legacy:
        value: >-
          mode_id == music_mode::energetic or mode_id == music_mode::rhythm or
          mode_id == music_mode::spectrum or mode_id == music_mode::rolling
      style:
        value: 'mode_id == music_mode::rhythm ? settings.as<rhythm_settings>.style : 0'
      has_fixed_colour:
        value: >-
          mode_id == music_mode::rhythm ? settings.as<rhythm_settings>.has_fixed_colour :
          (mode_id == music_mode::spectrum or mode_id == music_mode::rolling) ?
          settings.as<colour_settings>.has_fixed_colour : 0
      rgb:
        value: >-
          mode_id == music_mode::rhythm ? settings.as<rhythm_settings>.rgb :
          settings.as<colour_settings>.rgb
  rhythm_settings:
    seq:
      - id: style
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
  colour_settings:
    seq:
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: unknown_tail
        size-eos: true
  opaque_settings:
    seq:
      - id: unknown_tail
        size-eos: true
