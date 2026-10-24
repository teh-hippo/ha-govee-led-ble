meta:
  id: h6199_dreamview_frame
  title: H6199 legacy DreamView group controls
  endian: be
doc: |
  SPECULATIVE H6199 issue #438.  Legacy group controls use independent
  command opcodes and seventeen-byte bodies, not the newer module-0x60
  group layout.  Same brightness alone uses module 0x60 command 0x04;
  its admission requires main hardware 3.02.01 and firmware 1.09.00.
  The product fallback is five members, independently of the seventeen
  brightness bytes and ten connection bytes returned by individual reads.
  Member records use the shared A3 type-0x50 layout.  Completion replies
  match protocol and command with a zero success byte; they establish
  acceptance, not membership, rendering or synchronisation.
  Issue #294 reports an enable-query response, not group qualification.
  Official-app captures, revision differences, negative completion replies,
  reply tails, slot identity and maximum capacity remain unqualified.
params:
  - id: is_query
    type: bool
seq:
  - id: header
    type: u1
    enum: header
    valid:
      any-of: [header::write, header::read]
  - id: command
    type: u1
    enum: command
    valid:
      any-of: [command::member_connect, command::member_brightness, command::saturation, command::video_settings, command::sound, command::switch_group, command::delete_group, command::same_brightness]
  - id: body
    size: 17
    type:
      switch-on: 'is_query ? 0 : header.to_i'
      cases:
        0: query_body
        0x33: write_body
        0xaa: status_body
  - id: checksum
    type: u1
instances:
  body_size:
    value: 17
  discriminator_size:
    value: 'command == command::same_brightness ? 1 : 0'
  discriminator_value:
    value: 0x04
types:
  query_body:
    seq:
      - id: discriminator
        contents: [0x04]
        if: _root.command == command::same_brightness
      - id: unknown
        size-eos: true
  write_body:
    seq:
      - id: discriminator
        contents: [0x04]
        if: _root.command == command::same_brightness
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness or _root.command == command::sound
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
      - id: discriminator
        contents: [0x04]
        if: _root.command == command::same_brightness
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness or _root.command == command::sound
      - id: brightness_bytes
        size: 17
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
  acknowledgement:
    seq:
      - id: header
        type: u1
        enum: ack_header
        valid:
          any-of: [ack_header::upload, ack_header::write]
      - id: operation
        type: u1
        enum: ack_operation
        valid:
          expr: (header == ack_header::upload and operation == ack_operation::replace_group) or (header == ack_header::write and operation == ack_operation::delete_group)
      - id: status
        type: u1
      - id: unknown
        size: 16
      - id: checksum
        type: u1
    instances:
      is_success:
        value: status == 0
  upload_frame:
    seq:
      - id: header
        contents: [0xa3]
      - id: index
        type: u1
      - id: chunk
        size: 17
      - id: checksum
        type: u1
enums:
  header:
    0x33: write
    0xaa: read
  command:
    0x43: member_connect
    0x50: member_brightness
    0x51: saturation
    0x52: video_settings
    0x53: sound
    0x54: switch_group
    0x56: delete_group
    0x60: same_brightness
  apply_area:
    0: all
    1: part
  content_mode:
    0: game
    1: movie
  ack_header:
    0x33: write
    0xa3: upload
  ack_operation:
    0x50: replace_group
    0x56: delete_group
