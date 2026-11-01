meta:
  id: h607c_dreamview_frame
  title: H607C candidate Music DreamView module controls
  endian: le
doc: |
  SPECULATIVE H607C, support request #507, owner confirmations #511.
  Compatibility hypothesis: module 60 uses a single group-enable boolean
  without the camera discriminator. Delete is command 07 with ff.
  Native music activation has a type, two-byte selector, second parameter
  and sensitivity. Individual brightness and connection replies retain
  every slot, including zeros. No slot implies occupied membership.
  Mode eligibility, results, freshness and rendering require qualification.
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
instances:
  body_size:
    value: 16
  module_value:
    value: 0x60
  discriminator_size:
    value: 0
types:
  acknowledgement:
    seq:
      - id: header
        contents: [0x33, 0x60]
      - id: operation
        type: u1
        enum: command
      - id: status
        type: u1
      - id: unknown
        size: 15
      - id: checksum
        type: u1
    instances:
      is_success:
        value: status == 0
  query_body:
    seq:
      - id: unknown
        size-eos: true
  write_body:
    seq:
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness
      - id: music
        type: music_parameters
        if: _root.command == command::music
      - id: level
        type: u1
        if: _root.command == command::member_brightness
      - id: index
        type: u1
        if: _root.command == command::member_brightness or _root.command == command::member_connect
      - id: connected
        type: u1
        if: _root.command == command::member_connect
      - id: clear
        contents: [0xff]
        if: _root.command == command::delete_group
      - id: unknown
        size-eos: true
  music_parameters:
    seq:
      - id: music_type
        type: u1
      - id: selector
        type: u2le
      - id: second_parameter
        type: u1
      - id: sensitivity
        type: u1
  status_body:
    seq:
      - id: enabled
        type: u1
        if: _root.command == command::switch_group or _root.command == command::same_brightness
      - id: music
        type: music_parameters
        if: _root.command == command::music
      - id: brightness_bytes
        size: 16
        if: _root.command == command::member_brightness
      - id: connection_bytes
        size: 10
        if: _root.command == command::member_connect
      - id: unknown
        size-eos: true
enums:
  header:
    0x33: write
    0xaa: read
  command:
    1: switch_group
    2: music
    3: member_brightness
    4: same_brightness
    5: member_connect
    7: delete_group
