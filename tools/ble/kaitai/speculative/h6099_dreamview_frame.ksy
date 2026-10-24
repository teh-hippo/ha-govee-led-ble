meta:
  id: h6099_dreamview_frame
  title: H6099 MovieFeastV2 module commands and individual reads
  endian: be
doc: |
  SPECULATIVE H6099 issue #258, H66A0 issue #408.  Android 7.6.01 MovieFeastV2
  control selects module 0x60.  Group switch writes {on, 1}, queries with
  discriminator 1, and reads the first reply byte as on.  Individual module 0x60
  commands establish the member brightness, member connection, same brightness,
  saturation, video settings, sound, and delete layouts.  Brightness reads consume all
  16 returned bytes; connection reads copy 10 bytes (goods type 191 supports
  seven members; goods type 327 H66A0 supports ten members).  Never trim zeros
  or infer membership from slots.  Video settings encode apply area (0 All,
  1 Part) and content mode (0 Game, 1 Movie).  Issue #430 reports H66A0
  Part/Game and Part/Movie writes and individual readback while the group stays
  connected.  Unknown values remain raw bytes.  Unknown trailing bytes,
  slot occupancy, and reply freshness beyond
  request timing are unresolved.  No digest 0x0c or camera heuristic is
  modelled.  The H66A0 owner reports in issue #408 that writes for 0x01, 0x03,
  0x04, 0x05, 0x09, 0x0b and 0x0d match official-app captures, alongside the
  brightness query and a parsed connection reply.  Attributable raw captures
  are not attached.  Other reads remain structurally evidenced candidates.
  No official-app capture or owner qualification exists
  for H6099.
  This root does not model command ACKs.
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
      - id: apply_area
        type: u1
        enum: apply_area
        if: _root.command == command::video_settings
      - id: content_mode
        type: u1
        enum: content_mode
        if: _root.command == command::video_settings
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
      - id: apply_area
        type: u1
        enum: apply_area
        if: _root.command == command::video_settings
      - id: content_mode
        type: u1
        enum: content_mode
        if: _root.command == command::video_settings
      - id: softness
        type: u1
        if: _root.command == command::sound
      - id: unknown
        size-eos: true
enums:
  header:
    0x33: write
    0xaa: read
  apply_area:
    0: all
    1: part
  content_mode:
    0: game
    1: movie
  command:
    0x01: switch_group
    0x03: member_brightness
    0x04: same_brightness
    0x05: member_connect
    0x09: saturation
    0x0a: video_settings
    0x0b: sound
    0x0d: delete_group
