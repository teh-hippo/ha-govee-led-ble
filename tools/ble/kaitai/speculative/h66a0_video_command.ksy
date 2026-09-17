meta:
  id: h66a0_video_command
  endian: le
doc: |
  SPECULATIVE H66A0 video-only fixture for issues #257 and #297. Based on
  Fredde87/ha-govee-led-ble round2 command_write.ksy video_body_h66a0 and
  pact_tvlightv4/detail/mode/VideoVm. Contributor reports app preset reads
  08 Vivid, 09 Solid, 0a Smooth, 0b Delicate and a separate opaque byte.
  Independent captures, firmware coverage and owner qualification remain
  unresolved. This codec does not register H66A0 as a supported model.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    contents: [0x05]
  - id: mode
    contents: [0x00]
  - id: detail
    type: video_body
    size: 16
  - id: checksum
    type: u1
enums:
  video_source:
    0: movie
    1: game
  picture_preset:
    0x08: vivid
    0x09: solid
    0x0a: smooth
    0x0b: delicate
types:
  video_body:
    seq:
      - id: source
        type: u1
        enum: video_source
      - id: picture_preset
        type: u1
        enum: picture_preset
      - id: saturation
        type: u1
      - id: sound_effects
        type: u1
      - id: opaque
        type: u1
      - id: softness
        type: u1
