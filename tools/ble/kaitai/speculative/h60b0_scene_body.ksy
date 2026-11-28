meta:
  id: h60b0_scene_body
  title: H60B0 combined RGBIC and ripple scene body
  endian: be
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H60B0 combined scene structure.
  Canonical bodies retain marker 51 and the RGBIC section's marker 0a.
  H60B0 hardware accepted subtype 5a using the transformed upload below.
  Hardware also accepted an A3 route represented by subtype 0a with the
  51/length wrapper and nested 0a removed from the body. The two routes
  looked the same by eye against the Platform API, so subtype 5a remains
  the qualified preferred route.
  The bottom zone did not illuminate on either route.
  Catalogue activation retains its own selector; authored combinations use 510.
  Speed pages address each engine's own record index independently.
  Ripple records and both sections preserve unqualified suffix bytes. These
  observations are LAN visual checks, not BLE capture or exact-animation proof.
seq:
  - id: marker
    contents: [0x51]
  - id: len_rgbic
    type: u2
  - id: rgbic
    size: len_rgbic
    type: rgbic_section
  - id: len_ripple
    type: u2
  - id: ripple
    size: len_ripple
    type: ripple_section
  - id: unknown_tail
    size-eos: true
enums:
  upload_subtype:
    0x0a: rgbic_scene
    0x5a: combined
  activation_selector:
    510: temporary
types:
  upload:
    seq:
      - id: len_rgbic
        type: u2
      - id: rgbic
        size: len_rgbic
        type: rgbic_content
      - id: len_ripple
        type: u2
      - id: ripple
        size: len_ripple
        type: ripple_section
      - id: unknown_tail
        size-eos: true
  rgbic_section:
    seq:
      - id: marker
        contents: [0x0a]
      - id: body
        type: rgbic_content
  rgbic_content:
    seq:
      - id: num_records
        type: u1
      - id: records
        type: rgbic_record
        repeat: expr
        repeat-expr: num_records
      - id: unknown_tail
        size-eos: true
  rgbic_record:
    seq:
      - id: len_body
        type: u1
      - id: body
        size: len_body
        type: govee_shared::effect_layer
  ripple_section:
    seq:
      - id: num_records
        type: u1
      - id: records
        type: ripple_record
        repeat: expr
        repeat-expr: num_records
      - id: unknown_tail
        size-eos: true
  ripple_record:
    seq:
      - id: len_body
        type: u1
      - id: body
        size: len_body
        type: ripple_parameters
  ripple_parameters:
    seq:
      - id: effect
        type: u1
      - id: duration
        type: u2
      - id: movement_speed
        type: u1
      - id: movement
        type: u1
      - id: colour_mode
        type: u1
      - id: colour_speed
        type: u1
      - id: retention
        type: u2
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
      - id: unknown_tail
        size-eos: true
