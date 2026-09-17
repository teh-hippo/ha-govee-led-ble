meta:
  id: h6099_dreamview_frame
  title: H6099 MovieFeastV2 module commands and individual reads
  endian: be
doc: |
  SPECULATIVE H6099 issue #258. Android 7.6.01 AbsSingleFeastController selects
  module 0x60. MovieOpenControllerV2 writes {on,1}, queries with discriminator 1,
  and reads the first reply byte as on. controllerV2 MovieBrightnessController,
  MovieSubDeviceController, MovieSaturationController, MovieGetColorController,
  MovieSoundController and MovieDeleteController establish the named layouts;
  FeastBrightnessUniteController supplies same brightness. Brightness reads
  consume all returned bytes; connection reads copy ten bytes even though goods
  191 supports seven members. Never trim zeros or infer membership from slots.
  Sample bytes are preserved without assigning UI labels. Unknown trailing
  bytes, slot occupancy and reply freshness beyond request timing are unresolved.
  No digest 0x0c or camera heuristic. No official-app capture or owner
  qualification exists for H6099. This root does not model command ACKs.
params:
  - id: is_query
    type: bool
seq:
  - id: header
    type: u1
    enum: header
  - id: module
    contents: [0x60]
  - id: command
    type: u1
    enum: command
  - id: body
    size: 16
    type:
      switch-on: 'is_query ? 0 : header.to_i'
      cases:
        0: query_body
        0x33: write_body
        0xaa: status_body
  - id: checksum
    type: u1
types:
  query_body:
    seq:
      - id: discriminator
        contents: [1]
        if: _root.command == command::switch_group
      - id: unknown
        size-eos: true
  write_body:
    seq:
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness or _root.command == command::sound
      - id: discriminator
        contents: [1]
        if: _root.command == command::switch_group
      - id: level
        type: u1
        if: _root.command == command::member_brightness
      - id: index
        type: u1
        if: _root.command == command::member_brightness or _root.command == command::member_connect
      - id: connected
        type: u1
        if: _root.command == command::member_connect
      - id: saturation
        type: u1
        if: _root.command == command::saturation
      - id: sample_first
        type: u1
        if: _root.command == command::sample
      - id: sample_second
        type: u1
        if: _root.command == command::sample
      - id: softness
        type: u1
        if: _root.command == command::sound
      - id: unknown
        size-eos: true
  status_body:
    seq:
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness or _root.command == command::sound
      - id: brightness_bytes
        size: 16
        if: _root.command == command::member_brightness
      - id: connection_bytes
        size: 10
        if: _root.command == command::member_connect
      - id: saturation
        type: u1
        if: _root.command == command::saturation
      - id: sample_first
        type: u1
        if: _root.command == command::sample
      - id: sample_second
        type: u1
        if: _root.command == command::sample
      - id: softness
        type: u1
        if: _root.command == command::sound
      - id: unknown
        size-eos: true
enums:
  header:
    0x33: write
    0xaa: read
  command:
    0x01: switch_group
    0x03: member_brightness
    0x04: same_brightness
    0x05: member_connect
    0x09: saturation
    0x0a: sample
    0x0b: sound
    0x0d: delete_group
