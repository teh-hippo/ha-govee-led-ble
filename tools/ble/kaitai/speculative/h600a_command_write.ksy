meta:
  id: h600a_command_write
  title: Govee H600A whole-bulb logical BLE commands
  endian: be
  imports:
    - ../govee_shared
doc: |
  H600A.
  Compatibility hypothesis: known Pact 1/1 and 2/1 controllers use shared
  power and percentage brightness commands, mode 0D with direct RGB,
  big-endian Kelvin and companion RGB, and little-endian 16-bit scene/DIY
  selectors. Explicit Kelvin uses direct FFFFFF and the ordered shared
  2700..6500 K table. Frames are zero-padded and XOR-checksummed.
  Physical acceptance, encryption, revision differences and response timing
  remain unqualified; no attributable device evidence is available.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
  - id: checksum
    type: u1
instances:
  is_static:
    value: 'opcode == command_op::mode and body.as<mode_body>.sub_mode == mode_sel::static_colour'
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
  mode_sel:
    0x04: scene
    0x0a: diy
    0x0d: static_colour
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        valid:
          any-of: [0, 1]
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  brightness_body:
    seq:
      - id: percent
        type: u1
        valid:
          min: 1
          max: 100
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
      - id: detail
        size: 16
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::scene': scene_body
            'mode_sel::diy': diy_body
            'mode_sel::static_colour': static_colour_body
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  diy_body:
    seq:
      - id: code
        type: u2le
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  static_colour_body:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: companion_rgb
        type: govee_shared::rgb
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0]
