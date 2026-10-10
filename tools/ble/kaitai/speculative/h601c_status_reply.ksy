meta:
  id: h601c_status_reply
  title: Govee H601C basic AA status envelope
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H601C support request (feat/h60a-h601c-support; issue number
  not supplied). Compatibility hypothesis from Android 7.6.01 goods 111's
  bulblightv3/ble/Mode.java and SubModeColor.java:96-100,108-110:
  AA050D carries direct RGB at bytes 3..5, big-endian Kelvin at 6..7,
  companion RGB at 8..10; bytes 11..18 are ignored and remain opaque.
  Shared switch, brightness and soft/hard-version controllers supply the
  remaining basic domains. AbsModeController.p produces AA0501 queries;
  reuse status_query for the shared query envelope. Unknown domains/modes
  remain raw, never inferred effects. Physical acceptance, response presence,
  identity encoding across revisions and encryption remain unqualified.
  These are static-derived layouts, not official-app BLE captures.
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
      - id: brightness_pct
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
            'color_mode::static_colour': static_colour_body
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
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: unknown_tail
        size-eos: true
