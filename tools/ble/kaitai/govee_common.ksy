meta:
  id: govee_common
  title: Govee H617A shared BLE wire datatypes (imported by the per-payload specs)
  endian: le
  imports:
    - govee_shared
types:
  a3_header:
    seq:
      - id: marker
        contents: [0x01]
      - id: linecount
        type: u1
        valid:
          min: 2
  diy_selector:
    seq:
      - id: code
        type: u2le
  music_selector:
    doc: >
      Android 7.6.01 dreamcolorlightv1/ble/SubModeMusicV3.getWriteBytes/parse:
      new modes carry only mode and sensitivity. Legacy fixed colour is a
      zero/nonzero flag, not a palette count. Uninterpreted suffix stays opaque.
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
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
    instances:
      is_legacy:
        value: >-
          mode_id == music_mode::rhythm or mode_id == music_mode::spectrum or
          mode_id == music_mode::energetic or mode_id == music_mode::rolling
enums:
  music_mode:
    0x05: energetic
    0x03: rhythm
    0x04: spectrum
    0x06: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
