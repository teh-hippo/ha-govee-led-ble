meta:
  id: h6199_control_payload
  title: H6199 installation, Gradient and DIY selector payloads
  endian: le
doc: |
  SPECULATIVE H6199 additions for issue #294. Android 7.6.01 exact-model
  CameraSettingsAc and VM4Light plus direct register tests on HW3.02.01,
  FW1.10.04, WiFi HW1.03.00/FW1.00.33, Pact2/1 establish the hypothesis.
  These are NOT official-app BLE captures or schema promotion evidence.
  Direction 0/1 means clockwise/anticlockwise; camera position 0/1 top/bottom.
  Camera 0 absent and 2 incompatible are APK-only; only 1 healthy was tested.
  A3 and static detail expose Color > Subsection > Gradient, not HA transition
  duration or a proven visual blending algorithm. DIY code254 readback does
  not establish populated content, uploads or playback. Other revisions and
  unknown tails remain unqualified. See docs/h6199-native-controls.md.
seq:
  - id: value
    type: u1
  - id: unknown_tail
    size-eos: true
enums:
  camera_status:
    0: absent
    1: healthy
    2: incompatible
types:
  write_value:
    seq:
      - id: value
        type: u1
      - id: unknown_tail
        size-eos: true
  camera_state:
    seq:
      - id: value
        type: u1
        enum: camera_status
      - id: unknown_tail
        size-eos: true
  diy_selector:
    seq:
      - id: code
        type: u2
      - id: unknown_tail
        size-eos: true
  static_detail:
    seq:
      - id: gradient
        type: u1
      - id: unknown_tail
        size-eos: true
