meta:
  id: h6125_wire_write
  title: Govee H6125 speculative wire writes that differ from the shared logical frames
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6125, issue #117.
  Evidence source class: application producers and public legacy observations.
  Compatibility hypothesis: pact 1 uses a scaled brightness register and the
  0x11 music selector. Older controllers use 0x0b RGB with a segment mask;
  the original H612526 music selector is 0x0c with a separate mode codebook.
  The adapter re-encodes shared logical commands through these named fields.
  Revision eligibility belongs to the product profile, not this wire grammar.
  Unresolved assumptions: conflicting minimum-register evidence on some Telink
  paths, firmware-specific acceptance, unused bytes and command echoes.
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
    0x0c: legacy_music
    0x11: music
  legacy_music_mode:
    0x00: energetic
    0x04: rhythm
    0x03: spectrum
    0x02: rolling
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
            'mode_sub::legacy_music': legacy_music_selector
            'mode_sub::music': music_selector
  legacy_colour:
    seq:
      - id: rgb
        type: govee_shared::rgb
      - id: segment_mask
        type: u2le
      - id: padding
        size: 11
  legacy_music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: legacy_music_mode
      - id: sensitivity
        type: u1
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'legacy_music_mode::energetic': opaque_settings
            _: colour_settings
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
