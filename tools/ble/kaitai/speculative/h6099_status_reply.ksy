meta:
  id: h6099_status_reply
  title: Govee H6099 logical status reply
  endian: le
  imports:
    - ../govee_shared
    - ../govee_segment_page
doc: |
  SPECULATIVE H6099 reply frame for issue #258, ported from the issue branch
  and checked against Android 7.6.01 pact_h6099/detail/Info4Detail constructor:
  AA 05 15 contains a flag followed by big-endian Kelvin, zero for RGB.
  Its music parser and ble/v1/SubModeMusicV1.parse return after mode/sensitivity
  for new music; the remaining bytes are not legacy style or fixed colour.
  Sub4Diy.parse reads a little-endian code. Support.getColorPieceSize and
  getOneGroupColorSize select 14 zones in four-slot pages. Unused final records
  remain opaque. Owner qualification, firmware differences and unknown tails
  are unresolved; static readback does not contain rendered RGB.
  ControllerIcNum queries AA40 with no payload. NewDetailVm$connectBleSuc$1
  reads its first two payload bytes using BleUtil.getSignedShort (big endian)
  into Info4Detail.z0; Info4BleIotDevice.q() supplies physical count to MusicMode.
  PairAcV1's WifiHardVersionController (20) and WifiSoftVersionController (21)
  decode ASCII identity. detail/Info4Detail uses BlackBorderRemoveController:
  A9 0B length 01 followed by the enabled byte. No owner capture yet.
  pact_h6099 ComposeCalibrationDirection reads the first AA30 payload byte.
  HasCameraController and base2light CheckCameraVmInterface query AA32 and
  read its first byte: VideoModeViewInterface/AbsVideoMode distinguish 0 absent,
  1 healthy, 2 incompatible. Missing replies are not evidence of absence.
  Direction image orientations and other camera values remain unknown; 31 is
  camera position, not health. These are standalone reads, not calibration.
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
        'status_domain::power': power_body
        'status_domain::brightness': brightness_body
        'status_domain::firmware': version_body
        'status_domain::hardware': hardware_version_body
        'status_domain::physical_ic_count': physical_ic_count_body
        'status_domain::subordinate_20': version_body
        'status_domain::subordinate_21': version_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::display_setting': display_setting_body
        'status_domain::relative_brightness': relative_brightness_body
        'status_domain::segments': govee_segment_page(14, 4, false)
        'status_domain::installation_direction': installation_direction_body
        'status_domain::camera_health': camera_health_body
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x40: physical_ic_count
    0x20: subordinate_20
    0x21: subordinate_21
    0x30: installation_direction
    0x32: camera_health
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
  display_setting:
    0x06: scalar_white_balance
    0x0a: blank_screen
    0x0b: black_border
  camera_health:
    0: absent
    1: healthy
    2: incompatible
  blank_screen_detection:
    0x01: low_brightness
    0x02: same_tone
  mode_sel:
    0x00: video
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static_colour
  video_source:
    0x00: movie
    0x01: game
  video_region:
    0x08: part
    0x09: all
types:
  installation_direction_body:
    seq:
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  camera_health_body:
    seq:
      - id: value
        type: u1
        enum: camera_health
      - id: unknown_tail
        size-eos: true
  physical_ic_count_body:
    seq:
      - id: count
        type: s2be
      - id: unknown_tail
        size-eos: true
  display_setting_body:
    seq:
      - id: setting
        type: u1
        enum: display_setting
      - id: len
        type: u1
      - id: payload
        size: len
        type:
          switch-on: setting
          cases:
            'display_setting::scalar_white_balance': scalar_white_balance_state
            'display_setting::blank_screen': blank_screen_state
            'display_setting::black_border': black_border_state
      - id: unknown_tail
        size-eos: true
  scalar_white_balance_state:
    seq:
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  blank_screen_state:
    seq:
      - id: is_enabled
        type: u1
      - id: detection
        type: u1
        enum: blank_screen_detection
      - id: low_brightness_duration_seconds
        type: u2
      - id: same_tone_duration_seconds
        type: u2
      - id: unknown_tail
        size-eos: true
  black_border_state:
    seq:
      - id: is_enabled
        type: u1
      - id: unknown_tail
        size-eos: true
  relative_brightness_body:
    seq:
      - id: selector
        contents: [0x01]
      - id: edge_count
        type: u1
      - id: left_percent
        type: u1
      - id: top_percent
        type: u1
      - id: right_percent
        type: u1
      - id: bottom_percent
        type: u1
      - id: strip_left_percent
        type: u1
      - id: strip_right_percent
        type: u1
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
            'mode_sel::video': video_state
            'mode_sel::music': music_state
            'mode_sel::scene': scene_state
            'mode_sel::diy': diy_state
            'mode_sel::static_colour': static_state
  static_state:
    seq:
      - id: sub
        type: u1
      - id: kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  music_state:
    seq:
      - id: mode
        type: u1
      - id: sensitivity
        type: u1
      - id: is_calm
        type: u1
        if: is_legacy
      - id: has_fixed_colour
        type: u1
        if: is_legacy
      - id: fixed_colour
        type: govee_shared::rgb
        if: is_legacy
      - id: unknown_tail
        size-eos: true
    instances:
      is_legacy:
        value: mode == 3 or mode == 4 or mode == 5 or mode == 6
  video_state:
    seq:
      - id: source
        type: u1
        enum: video_source
      - id: region
        type: u1
        enum: video_region
      - id: saturation
        type: u1
      - id: sound_effects
        type: u1
      - id: sound_type
        type: u1
      - id: softness
        type: u1
      - id: unknown_tail
        size-eos: true
  scene_state:
    seq:
      - id: scene_id
        type: u2le
  diy_state:
    seq:
      - id: code
        type: u2le
  power_body:
    seq:
      - id: is_on
        type: u1
  brightness_body:
    seq:
      - id: percent
        type: u1
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
  hardware_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
