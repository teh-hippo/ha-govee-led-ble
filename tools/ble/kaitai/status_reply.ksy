meta:
  id: status_reply
  title: Govee H617A "aa" status-reply envelope (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
doc: |
  H617A 20-byte status reply. The final byte is the XOR of bytes 0 through 18.
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
        'aa_domain::segments': segments_body
        'aa_domain::multi_effect': multi_effect_body
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
    0x15: static
    0x04: scene
    0x0a: diy
    0x13: music
types:
  multi_effect_body:
    seq:
      - id: flag
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
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
            'color_mode::diy': govee_common::diy_selector
            'color_mode::music': govee_common::music_selector
  cm_static:
    seq:
      - id: sub
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  cm_scene:
    seq:
      - id: scene_id
        type: u2le
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  hw_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  segments_body:
    seq:
      - id: group
        type: u1
        valid:
          min: 1
          max: 5
      - id: segments
        type: segment
        repeat: expr
        repeat-expr: 3
        if: group >= 1 and group <= 5
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  segment:
    seq:
      - id: brightness
        type: u1
      - id: colour
        type: govee_shared::rgb
