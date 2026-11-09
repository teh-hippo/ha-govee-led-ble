meta:
  id: h61f5_extended_static_write
  title: H61F5 candidate extended static control envelope
  endian: le
  imports:
    - ../command_write
doc: |
  SPECULATIVE: H61F5 static RGB, Kelvin and relative-brightness controls for
  installed layouts above sixteen logical sections, up to the qualified
  twenty-section product capacity. Selection uses three bytes, least
  significant byte and bit first. Smaller layouts retain the narrow root.
  Extended hardware operation remains unconfirmed. Unused suffix bytes
  remain opaque rather than validated as zeroes.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
    valid: command_op::multi
  - id: body
    size: 17
    type: multi_cmd
  - id: checksum
    type: u1
instances:
  static_prefix:
    value: '[0x33, command_op::multi.to_i, multi_sub::static.to_i]'
  minimum_segment_count:
    value: 17
  is_static:
    value: body.sub_body.static_sub == 1 or body.sub_body.static_sub == 2
enums:
  command_op:
    0x05: multi
  multi_sub:
    0x15: static
types:
  multi_cmd:
    seq:
      - id: sub
        type: u1
        enum: multi_sub
        valid: multi_sub::static
      - id: sub_body
        size: 16
        type: command_write::static_cmd(true)
