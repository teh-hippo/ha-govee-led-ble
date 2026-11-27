meta:
  id: h66a0_video_command
  endian: le
doc: |
  SPECULATIVE H66A0 video command layout.  Closed owner-confirmation issue #450
  (https://github.com/teh-hippo/ha-govee-led-ble/issues/450) records standalone
  Video Movie as visibly working on Supported H66A0 HW 3.07.01/FW 1.00.24.
  It separately records Game/Movie switching in DreamView sync-centre mode,
  which is a distinct control path; standalone Game remains unconfirmed.  The
  owner evidence qualifies those visible operations, not every byte here.
  A contributor's round2 command_write.ksy video_body_h66a0 layout associates
  preset reads with 08 Vivid, 09 Solid, 0a Smooth and 0b Delicate, plus a
  separate opaque byte.  Other byte meanings, valid ranges, wire values and
  other hardware or firmware revisions remain unqualified.
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
