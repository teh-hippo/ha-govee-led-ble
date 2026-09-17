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
  Evidence source class: reachable Android 7.6.01 producer/consumer code.
  Compatibility hypothesis: the modern
  DreamColor route uses the shared power/brightness/identity/mode fields and
  fifteen logical segments in five three-record A5 pages. No official-app BLE
  capture or complete owner readback qualification is available.
  Android 7.6.01 sources, relative to full/sources/com/govee/:
  base2home/pact/support/OldDreamColorUtil.java:149-152,226-249,367-374 routes
  H6102 to DreamColor goods 18; 1.03.01 is migration, not a wire predicate.
  dreamcolorlightv1/adjust/AdjustAc.e2 -> adjust/v1/FrameV1.h -> UiV3
  (isSupportProtocol:820-832; Support.addSupportPact:383-394 for goods 18,
  Pact 10) -> BleOpV3.java:716 uses SwitchController,
  BrightnessController, SoftVersionController, HardVersionController,
  ModeController and BulbStringColorControllerV2; the last dispatches to
  dreamcolorlightv1/ble/BulbGroupColorV2.java:22-38, consuming only group +
  three brightness/RGB records. The final four bytes are ignored, not zeroes.
  dreamcolorlightv1/ble/Mode.java:80-115 dispatches mode replies;
  SubModeColorV2.java:595-601 consumes gradual flag and big-endian Kelvin;
  SubModeScenes.parse and SubModeNewDiy.parse consume little-endian codes.
  Gradual4BleWifiController.java:55-63 consumes AA A3's first payload byte.
  LimitController.java:25-38 writes 33 0E and consumes AA 0E boolean state;
  the app gates this setting at HW >=1.00.02. Unknown tails remain opaque.
  See H6102.md beside this schema for outbound reachability and deferred legacy.
  Unresolved assumptions: physical mapping/IC count, firmware-specific response presence,
  legacy mode/readback layouts, unknown mode selectors and all unused bytes.
  Preserve these bytes; this root does not enable legacy RGB or A1 DIY writes.
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
      - id: brightness_pct
        type: u1
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
        doc: Gradual flag from SubModeColorV2.parse; not the write operation byte.
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
