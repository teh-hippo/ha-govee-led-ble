meta:
  id: h7025_diy_body
  title: Govee H7025 native DIY upload
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
doc: |
  SPECULATIVE: exact H7025 native DIY records reconstructed from the product
  authoring implementation, not independently captured from BLE.  The
  A3/58 upload contains one sub-effect and activates through the disposable
  DIY selector 254.  Unknown revisions and visible playback remain unqualified.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x58]
  - id: body
    type: body
  - id: padding
    size-eos: true
types:
  body:
    seq:
      - id: sub_effect
        type: u1
        enum: sub_effect
      - id: tail
        type:
          switch-on: sub_effect
          cases:
            'sub_effect::retrace': retrace
            'sub_effect::spray': spray
            'sub_effect::streamer': streamer
            'sub_effect::glimmer': glimmer
            'sub_effect::star_flash': star_flash
            'sub_effect::pile_up': pile_up
  palette:
    seq:
      - id: count
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: count
  retrace:
    seq:
      - id: speed
        type: u1
      - id: quantity
        type: u1
      - id: palette
        type: palette
  spray:
    seq:
      - id: speed
        type: u1
      - id: variant
        type: u1
      - id: injections
        type: u1
      - id: interval
        type: u1
      - id: palette
        type: palette
  streamer:
    seq:
      - id: speed
        type: u1
      - id: direction
        type: u1
      - id: reverse
        type: u1
        valid:
          any-of: [0, 1]
      - id: palette
        type: palette
  glimmer:
    seq:
      - id: speed
        type: u1
      - id: density
        type: u1
      - id: palette
        type: palette
  star_flash:
    seq:
      - id: speed
        type: u1
      - id: density
        type: u1
      - id: background
        type: govee_shared::rgb
      - id: palette
        type: palette
  pile_up:
    seq:
      - id: speed
        type: u1
      - id: direction
        type: u1
      - id: reverse
        type: u1
        valid:
          any-of: [0, 1]
      - id: palette
        type: palette
enums:
  sub_effect:
    12: retrace
    13: spray
    14: streamer
    15: glimmer
    16: star_flash
    17: pile_up
