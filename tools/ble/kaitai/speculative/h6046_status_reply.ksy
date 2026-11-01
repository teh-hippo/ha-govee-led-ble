meta:
  id: h6046_status_reply
  title: Govee H6046 status replies
  endian: le
  imports:
    - ../govee_shared
    - ../govee_segment_page
    - h6046_command_write
doc: |
  H6046.
  Evidence class: exact-model behavioural audit, not attributable captures or
  owner qualification. Known Pact 1/1 and 2/1 share this modern layout.
  Frames contain 20 bytes; the transport checks XOR of bytes 0..18 at byte 19.
  Ten segment records occupy pages 4+4+2. Unused final-page slots and unknown
  suffixes are retained, never required to be zero.
  Static status preserves independent left/right Kelvin, not an H6199 gradient
  flag. Music RX preserves two bar colours rather than the TX target mask.
  Scene/DIY status proves the selector, not uploaded content or rendering.
  Register 0x41 is decode-only knowledge and grants no query/write permission.
  Unresolved assumptions: initial static byte, suffix meanings, other revisions,
  version envelope variants and physical mixed native-white interpretation.
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
        'status_domain::colour_mode': colour_mode_body
        'status_domain::firmware': version_body
        'status_domain::hardware': hardware_version_body
        'status_domain::subordinate_20': version_body
        'status_domain::subordinate_21': version_body
        'status_domain::bar_enable': bar_enable_body
        'status_domain::power_off_memory': power_off_memory_body
        'status_domain::segments': govee_segment_page(10, 4, false)
  - id: checksum
    type: u1
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x20: subordinate_20
    0x21: subordinate_21
    0x33: bar_enable
    0x41: power_off_memory
    0xa5: segments
types:
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: unknown_tail
        size-eos: true
  brightness_body:
    seq:
      - id: percent
        type: u1
      - id: unknown_tail
        size-eos: true
  bar_enable_body:
    doc: Left bit 0x01 and right bit 0x10 are independent of master power.
    seq:
      - id: mask
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      left_enabled:
        value: (mask & 0x01) != 0
      right_enabled:
        value: (mask & 0x10) != 0
  power_off_memory_body:
    doc: |
      Decode-only register. The family recognises this setting, but no exact
      H6046 control eligibility is established. The family reads the second
      payload octet; the leading octet and remaining suffix are unknown.
    seq:
      - id: unknown_leading
        type: u1
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  hardware_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: h6046_command_write::mode_sel
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'h6046_command_write::mode_sel::static_colour': static_detail
            'h6046_command_write::mode_sel::scene': scene_detail
            'h6046_command_write::mode_sel::diy': diy_detail
            'h6046_command_write::mode_sel::music': music_detail
  static_detail:
    doc: |
      Unknown initial detail byte followed by big-endian left/right Kelvin.
      Zero is an explicit value, not absence. Unequal values must not become
      an aggregate Kelvin observation; rendered segment RGB is read separately.
    seq:
      - id: unknown_flag
        type: u1
      - id: left_kelvin
        type: u2be
      - id: right_kelvin
        type: u2be
      - id: unknown_tail
        size-eos: true
  scene_detail:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  diy_detail:
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
  music_detail:
    doc: |
      Modern Rhythm alone has the style byte. Base modes expose a fixed-colour
      flag then left/right RGB, even when automatic colour is selected.
      Companion-backed selections expose mode and sensitivity only; their
      uploaded palette remains retained content, not status readback.
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
          mode == h6046_command_write::music_mode::energetic or
          mode == h6046_command_write::music_mode::impact or
          mode == h6046_command_write::music_mode::spray
