meta:
  id: h1771_diy_body
  title: H1771 candidate dual-source DIY body
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H1771 DIY body reconstructed from model behaviour, not confirmed
  by device traffic.  The 0x58 multi-packet upload carries the root body;
  scene catalogue parameters add the 0x50 marker.  Section ordering is not
  yet mapped to physical sides.  Unknown variants and suffixes remain opaque.
seq:
  - id: len_body
    type: u2
  - id: body
    size: len_body
    type: sections
  - id: unknown_tail
    size-eos: true
enums:
  catalogue_family:
    957: native_scene
  first_effect:
    1: temperature
    2: palette_2
    3: palette_3
    4: palette_4
  second_effect:
    1: common_1
    2: common_2
    3: common_3
    4: common_4
    5: common_5
    6: palette_6
    7: streamer
    8: background
    10: stack
    11: breathe
    13: palette_13
    14: palette_14
    15: temperature
types:
  scene:
    seq:
      - id: marker
        contents: [0x50]
      - id: body
        type: h1771_diy_body
  sections:
    seq:
      - id: len_first
        type: u2
      - id: first
        size: len_first
        type: first_section
      - id: len_second
        type: u2
      - id: second
        size: len_second
        type: second_section
      - id: unknown_tail
        size-eos: true
  first_section:
    seq:
      - id: enabled
        type: u1
        if: _io.size > 0
      - id: effect
        type: u1
        enum: first_effect
        if: _io.size > 1 and enabled == 1
      - id: body
        size-eos: true
        type:
          switch-on: effect
          cases:
            'first_effect::temperature': temperature
            'first_effect::palette_2': speed_palette
            'first_effect::palette_3': speed_palette
            'first_effect::palette_4': speed_palette
        if: _io.size > 1 and enabled == 1
      - id: unknown_tail
        size-eos: true
  second_section:
    seq:
      - id: enabled
        type: u1
        if: _io.size > 0
      - id: effect
        type: u1
        enum: second_effect
        if: _io.size > 1 and enabled == 1
      - id: body
        size-eos: true
        type:
          switch-on: effect
          cases:
            'second_effect::common_1': common_palette
            'second_effect::common_2': common_palette
            'second_effect::common_3': common_palette
            'second_effect::common_4': common_palette
            'second_effect::common_5': common_palette
            'second_effect::palette_6': speed_palette
            'second_effect::streamer': two_parameter_palette
            'second_effect::background': background_palette
            'second_effect::stack': two_parameter_palette
            'second_effect::breathe': two_parameter_palette
            'second_effect::palette_13': speed_palette
            'second_effect::palette_14': speed_palette
            'second_effect::temperature': temperature
        if: _io.size > 1 and enabled == 1
      - id: unknown_tail
        size-eos: true
  temperature:
    seq:
      - id: speed
        type: u1
      - id: brightness
        type: u1
      - id: kelvin
        type: u2
      - id: unknown_tail
        size-eos: true
  speed_palette:
    seq:
      - id: speed
        type: u1
      - id: palette
        type: palette
      - id: unknown_tail
        size-eos: true
  common_palette:
    seq:
      - id: speed
        type: u1
      - id: variant
        type: u1
      - id: palette
        type: palette
      - id: unknown_tail
        size-eos: true
  two_parameter_palette:
    seq:
      - id: speed
        type: u1
      - id: parameter_1
        type: u1
      - id: parameter_2
        type: u1
      - id: palette
        type: palette
      - id: unknown_tail
        size-eos: true
  background_palette:
    seq:
      - id: speed
        type: u1
      - id: background
        type: govee_shared::rgb
      - id: palette
        type: palette
      - id: unknown_tail
        size-eos: true
  palette:
    seq:
      - id: num_colours
        type: u1
      - id: colours
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: num_colours
