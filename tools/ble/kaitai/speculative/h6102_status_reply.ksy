meta:
  id: h6102_status_reply
  title: Govee H6102 shared modern AA status envelope (decode-only)
  endian: le
  imports:
    - ../govee_segment_page
    - ../govee_common
    - ../govee_shared
doc: |
  SPECULATIVE H6102, issue #115.
  Evidence source class: reachable Android 7.6.01 protocol behaviour.
  Compatibility hypothesis: the modern DreamColor route (goods type 18, Pact 10)
  uses the shared power, identity, and mode fields and fifteen logical segments
  in five three-record A5 pages.  No official-app BLE capture or complete owner
  readback qualification is available.  The 1.03.01 firmware threshold is an app
  migration condition, not a wire predicate.  Segment page replies consume the
  one-based group and three brightness/RGB records; the final four bytes are
  ignored rather than validated as zeroes.  Mode replies carry a gradual flag and
  big-endian Kelvin for static colour (0x15), little-endian codes for scenes
  (0x04) and DIY (0x0a), and mode/sensitivity for music (0x13).  AA A3 carries
  the gradual boolean in its first payload byte, and AA 0E carries the limit
  boolean gated at HW >= 1.00.02.  Unknown tails remain opaque.
  See docs/h6102-application-findings.md for outbound reachability and deferred legacy.
  Unresolved assumptions: physical mapping/IC count, firmware-specific response presence,
  legacy mode/readback layouts, unknown mode selectors and all unused bytes.
  Preserve these bytes; this root does not enable legacy RGB or A1 DIY writes.
  Issue #310 supplies AA04 register EB from a Pact 1 device.  Master brightness
  is a raw 20..254 register for Pact 1 and a percentage for Pact 10; the
  effective profile selects the semantic conversion, not the reply value.
  The owner also reports register FF after another controller writes 255.
  Preserve the raw register and expose a Pact 1 upper-bound normalisation:
  the app accepts an unsigned reply byte and caps its display at register 254.
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
        'aa_domain::multi_effect': multi_effect_body
        'aa_domain::limit': multi_effect_body
        'aa_domain::segments': govee_segment_page(15, 3, false)
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x0e: limit
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
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
    instances:
      legacy_register:
        value: 'register > 254 ? 254 : register'
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
        enum: govee_common::music_mode
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
        value: >-
          mode_id == govee_common::music_mode::rhythm or mode_id == govee_common::music_mode::spectrum or
          mode_id == govee_common::music_mode::energetic or mode_id == govee_common::music_mode::rolling
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
