meta:
  id: h6125_status_reply
  title: Govee H6125 speculative AA status envelope (decode-only)
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_shared
    - h6102_status_reply
doc: |
  SPECULATIVE H6125, issue #117.
  Evidence source class: reachable Android 7.6.01 status-parsing behaviour; no
  official-app BLE capture of an identified H6125 is available.
  Compatibility hypothesis: the extended pact-1 route replies with the
  shared power, identity, static, scene, DIY and fifteen-segment layouts, plus a
  brightness register, the submode 0x11 music layout and the gradual register.
  In Android 7.6.01, mode replies carry a gradual flag and big-endian Kelvin for
  static colour (0x15), little-endian codes for scenes (0x04) and DIY (0x0a),
  and effect, sensitivity, and per-effect settings for music (0x11); segment
  pages carry three brightness/RGB records per group, and brightness replies
  return the raw register byte unchanged.
  Unresolved assumptions: register range for each hardware revision, whether the
  device ever answers with the legacy 0x0b static or 0x0c music modes, unused
  bytes of every reply, and whether segment pages contain meaningful records
  beyond fifteen.  Unknown mode selectors and every unused byte stay opaque.
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
        'aa_domain::segments': govee_segment_page(15, 3, false)
        'aa_domain::multi_effect': h6102_status_reply::multi_effect_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x11: music
    0x15: static
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
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: register
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
        doc: Zero is Dynamic and nonzero is Calm.
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
