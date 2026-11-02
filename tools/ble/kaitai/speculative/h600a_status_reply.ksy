meta:
  id: h600a_status_reply
  title: Govee H600A basic AA status envelope
  endian: be
  imports:
    - ../govee_shared
doc: |
  H600A.
  Compatibility hypothesis: AA0501 queries return mode 0D direct RGB,
  big-endian Kelvin and companion RGB, or 16-bit little-endian scene/DIY
  selection. Shared power, percentage brightness and version domains
  describe the remaining basic state. Unknown modes, domains, hardware
  prefix and tails remain opaque. Response availability, identity encoding
  across revisions, encryption and physical behaviour remain unqualified.
  No attributable device evidence is available.
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
        'aa_domain::colour_mode': colour_mode_body
        'aa_domain::firmware': version_body
        'aa_domain::hardware': hardware_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
  color_mode:
    0x04: scene
    0x0a: diy
    0x0d: static_colour
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
  colour_mode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::scene': scene_body
            'color_mode::diy': diy_body
            'color_mode::static_colour': static_colour_body
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: unknown_tail
        size-eos: true
  diy_body:
    seq:
      - id: code
        type: u2le
      - id: unknown_tail
        size-eos: true
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: companion_rgb
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
  hardware_body:
    seq:
      - id: unknown_prefix
        type: u1
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
