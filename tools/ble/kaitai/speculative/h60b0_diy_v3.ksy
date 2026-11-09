meta:
  id: h60b0_diy_v3
  title: H60B0 Pact 1/3 three-source native DIY upload
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H60B0 Pact 1/3 DIY, not hardware-confirmed.
  Upload subtype 58 and selector 254 are shared with older Pacts,
  but the body is incompatible. The u16 length excludes itself.
  Canonical shared content adds marker 50 outside this root.
  Sections address top, side and bottom in that order.
  Kelvin records retain their companion RGB values and unknown tails.
seq:
  - id: len_body
    type: u2
  - id: body
    type: sections
    size: len_body
  - id: unknown_tail
    size-eos: true
types:
  sections:
    seq:
      - id: len_top
        type: u1
      - id: top
        type: top
        size: len_top
      - id: len_side
        type: u1
      - id: side
        type: zone(false)
        size: len_side
      - id: len_bottom
        type: u1
      - id: bottom
        type: zone(true)
        size: len_bottom
      - id: unknown_tail
        size-eos: true
  top:
    seq:
      - id: flow_speed
        type: u1
      - id: direction
        type: u1
      - id: enabled
        type: u1
      - id: family
        type: u1
        if: enabled != 0
      - id: body
        type:
          switch-on: family
          cases:
            7: temperature
            _: colour_parameters(family, false)
        if: enabled != 0 and family != 1
      - id: unknown_tail
        size-eos: true
  zone:
    params:
      - id: bottom
        type: bool
    seq:
      - id: family
        type: u1
      - id: body
        type:
          switch-on: bottom
          cases:
            true: temperature_parameters(family)
            false: colour_parameters(family, true)
        if: family != 1
      - id: unknown_tail
        size-eos: true
  colour_parameters:
    params:
      - id: family
        type: u1
      - id: side
        type: bool
    seq:
      - id: speed
        type: u1
      - id: minimum_brightness
        type: u1
        if: family == 3 or family == 5
      - id: maximum_brightness
        type: u1
        if: family == 3 or family == 5
      - id: direction
        type: u1
        if: side and (family == 7 or family == 10 or family == 12)
      - id: background
        type: govee_shared::rgb
        if: side and family == 9
      - id: colourful
        type: u1
        if: side and (family == 9 or family == 13)
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
      - id: unknown_tail
        size-eos: true
  temperature:
    seq:
      - id: brightness
        type: u1
      - id: kelvin
        type: u2
      - id: companion
        type: govee_shared::rgb
      - id: unknown_tail
        size-eos: true
  temperature_parameters:
    params:
      - id: family
        type: u1
    seq:
      - id: speed
        type: u1
      - id: minimum_brightness
        type: u1
      - id: maximum_brightness
        type: u1
        if: family == 3
      - id: num_colours
        type: u1
      - id: colours
        type: kelvin_colour
        repeat: expr
        repeat-expr: num_colours
      - id: unknown_tail
        size-eos: true
  kelvin_colour:
    seq:
      - id: kelvin
        type: u2
      - id: companion
        type: govee_shared::rgb
