meta:
  id: h601c_command_write
  title: Govee H601C basic logical BLE commands
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H601C support request (feat/h60a-h601c-support; issue number
  not supplied). Android 7.6.01 bulblightv3/pact/Support.java registers goods
  111; bulblightv3/ble/SubModeColor.java:71-82,108-110 produces mode 0D,
  direct RGB, big-endian Kelvin and companion RGB. Explicit Kelvin uses
  direct FFFFFF and Constant.getTemColorByKelvin's first ordered match.
  Shared SwitchController/BrightnessController supply 01/04; the shared
  single-controller envelope pads writes with zeroes and appends XOR.
  Compatibility hypothesis: all identifiable H601C revisions use this basic
  producer, independently of Matter configuration. This is the logical frame;
  encryption selection, physical acceptance, revision differences and reply
  availability remain unqualified. No official-app BLE captures supplied.
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
            'mode_sel::static_colour': static_colour_body
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
