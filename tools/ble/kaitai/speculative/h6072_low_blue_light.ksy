meta:
  id: h6072_low_blue_light
  title: Govee H6072 low-blue-light setting
  endian: le
doc: |
  SPECULATIVE H6072 setting for owner confirmation #486.
  Method 1 carries enable, two opaque sibling fields, and a level.
  Sibling fields have no independently established control semantics.
  Unknown methods and values remain uninterpreted.
seq:
  - id: header
    type: u1
    enum: prefix
    valid: prefix::status
  - id: domain
    type: u1
    enum: operation
    valid: operation::low_blue_light
  - id: body
    type: state
  - id: padding
    size: 12
  - id: checksum
    type: u1
enums:
  prefix:
    0xaa: status
    0x33: write
  operation:
    0xba: low_blue_light
  method:
    1: scale
types:
  envelope:
    seq:
      - id: header
        type: u1
        enum: prefix
        valid:
          any-of: [prefix::status, prefix::write]
      - id: opcode
        type: u1
        enum: operation
        valid: operation::low_blue_light
      - id: payload
        size: 17
      - id: checksum
        type: u1
  state:
    seq:
      - id: method
        type: u1
        enum: method
      - id: enabled
        type: u1
      - id: sibling_1
        type: u1
      - id: sibling_2
        type: u1
      - id: level
        type: u1
    instances:
      minimum_level:
        value: 20
      maximum_level:
        value: 100
      is_supported:
        value: method == method::scale and enabled <= 1 and level >= minimum_level and level <= maximum_level
  write:
    seq:
      - id: header
        type: u1
        enum: prefix
        valid: prefix::write
      - id: opcode
        type: u1
        enum: operation
        valid: operation::low_blue_light
      - id: body
        type: state
        valid:
          expr: _.is_supported
      - id: padding
        size: 12
      - id: checksum
        type: u1
  query:
    seq:
      - id: header
        type: u1
        enum: prefix
        valid: prefix::status
      - id: opcode
        type: u1
        enum: operation
        valid: operation::low_blue_light
      - id: method
        type: u1
        enum: method
        valid: method::scale
      - id: padding
        contents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
      - id: checksum
        type: u1
