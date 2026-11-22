meta:
  id: h612a_extended_static_write
  title: Govee H612A static colour and brightness command envelope
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE: H612A static RGB, Kelvin and relative-brightness controls.
  The exact-product path selects up to 10 logical colour sections with a
  four-byte least-significant-bit-first mask.  Unused suffix bytes are retained
  as opaque data.  No complete owner capture is available yet.
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
    value: 1
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
        type: static_cmd
  segment_mask:
    seq:
      - id: bits
        type: u4le
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            1: static_color
            2: static_brightness
  static_color:
    seq:
      - id: rgb_direct
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: rgb_preview
        type: govee_shared::rgb
      - id: mask
        type: segment_mask
      - id: unknown_tail
        size-eos: true
    instances:
      tail_size:
        value: 3
  static_brightness:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
      - id: mask
        type: segment_mask
      - id: unknown_tail
        size-eos: true
    instances:
      tail_size:
        value: 10
