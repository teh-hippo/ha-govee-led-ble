meta:
  id: h6102_wire_write
  title: Govee H6102 Pact 1 wire writes that differ from the shared logical frames
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6102, issues #115, #310, and #424.
  Evidence source class: reachable Android 7.6.01 producer/consumer behaviour
  and owner-verified frames on Pact 1/1 (#310 and #424). No official-app BLE
  capture is available.
  Compatibility hypothesis: Pact 1 codes 1 and 2 use a 20..254 master
  brightness register and the 0x11 music selector; intermediate Pact 1
  revisions below HW 1.00.03 / FW 1.06.00 use 0x0b RGB with a 15-segment mask.
  The shared logical commands remain canonical; the exact-model profile
  transforms them into these wire writes. Pact 10 continues to use the shared
  modern wire frames.
  Unresolved assumptions: physical brightness calibration, reply freshness,
  write echo behaviour and unused bytes across firmware revisions.
  The final byte is the XOR of bytes 0 through 18.
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
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
  - id: checksum
    type: u1
enums:
  command_op:
    0x04: brightness
    0x05: mode
  mode_sub:
    0x0b: legacy_colour
    0x11: music
  music_mode:
    0x10: energetic
    0x11: rhythm
    0x12: spectrum
    0x13: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
types:
  brightness_body:
    seq:
      - id: register
        type: u1
      - id: padding
        size-eos: true
  mode_body:
    seq:
      - id: sub
        type: u1
        enum: mode_sub
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'mode_sub::legacy_colour': legacy_colour
            'mode_sub::music': music_selector
  legacy_colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: segment_mask
        type: u2le
      - id: padding
        size: 11
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'music_mode::rhythm': rhythm_settings
            'music_mode::spectrum': colour_settings
            'music_mode::rolling': colour_settings
            _: opaque_settings
  rhythm_settings:
    seq:
      - id: style
        doc: Zero is Dynamic and nonzero is Calm.
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: padding
        size-eos: true
  colour_settings:
    seq:
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: padding
        size-eos: true
  opaque_settings:
    seq:
      - id: padding
        size-eos: true
