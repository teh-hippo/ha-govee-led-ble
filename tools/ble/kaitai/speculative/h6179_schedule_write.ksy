meta:
  id: h6179_schedule_write
  title: Govee H6179 speculative clock and schedule write envelope
  endian: le
doc: |
  SPECULATIVE H6179 compatibility hypothesis: exact-SKU clock, timer, sleep,
  wake, and limit writes use a 20-byte 0x33 envelope with the compact candidate
  layouts below.
  Unresolved assumptions: no exact-model capture verifies the operation bytes,
  clock marker, field meanings, flag bits, repeat-mask semantics, opaque tails,
  or XOR checksum byte.
seq:
  - id: header
    contents: [0x33]
  - id: operation
    type: u1
    enum: operation
  - id: body
    size: 17
    type:
      switch-on: operation
      cases:
        'operation::clock': compact_clock_body
        'operation::limit': limit_body
        'operation::sleep': sleep_body
        'operation::wake': wake_body
        'operation::timer': timer_body
  - id: checksum
    type: u1
types:
  compact_clock_body:
    seq:
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: second
        type: u1
      - id: weekday
        type: u1
      - id: format_marker
        type: u1
      - id: timezone_hours
        type: s1
      - id: timezone_minutes
        type: u1
      - id: opaque
        size-eos: true
  limit_body:
    seq:
      - id: is_enabled
        type: u1
      - id: opaque
        size-eos: true
  timer_body:
    seq:
      - id: slot
        type: u1
      - id: enable_and_action
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: repeat_mask
        type: u1
      - id: opaque
        size-eos: true
    instances:
      is_enabled:
        value: '(enable_and_action & 0x80) != 0'
      turns_on:
        value: '(enable_and_action & 0x01) != 0'
      is_one_time:
        value: repeat_mask == 0x80
      repeats_every_day:
        value: repeat_mask == 0
      has_explicit_weekdays:
        value: '(repeat_mask & 0x80) != 0 and (repeat_mask & 0x7f) != 0'
      explicit_weekday_mask:
        value: 'repeat_mask & 0x7f'
  sleep_body:
    seq:
      - id: state
        type: u1
      - id: start_brightness
        type: u1
      - id: duration_minutes
        type: u1
      - id: remaining_minutes
        type: u1
      - id: opaque
        size-eos: true
    instances:
      is_enabled:
        value: state == 1
  wake_body:
    seq:
      - id: state
        type: u1
      - id: target_brightness
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: repeat_mask
        type: u1
      - id: duration_minutes
        type: u1
      - id: opaque
        size-eos: true
    instances:
      is_enabled:
        value: state == 1
      is_one_time:
        value: repeat_mask == 0x80
      repeats_every_day:
        value: repeat_mask == 0
      has_explicit_weekdays:
        value: '(repeat_mask & 0x80) != 0 and (repeat_mask & 0x7f) != 0'
      explicit_weekday_mask:
        value: 'repeat_mask & 0x7f'
enums:
  operation:
    0x09: clock
    0x0e: limit
    0x11: sleep
    0x12: wake
    0x23: timer
