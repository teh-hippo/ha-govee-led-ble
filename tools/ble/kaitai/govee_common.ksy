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
      - id: slot
        type: u1
      - id: type_byte
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
      - id: manual_color_count
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_color_count >= 1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
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
