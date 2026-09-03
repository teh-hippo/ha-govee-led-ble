meta:
  id: h6179_status_reply
  title: Govee H6179 speculative "aa" status-reply envelope
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6179 compatibility hypothesis: exact-SKU status replies use a
  20-byte 0xaa envelope with the candidate domain, mode, timer, sleep, wake,
  limit, version, brightness, and colour layouts below.
  Unresolved assumptions: no exact-model capture verifies any selector or field
  meaning, string encoding, timer count rule, optional music colour, opaque
  tails, or XOR checksum byte.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: status_domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'status_domain::power': power_body
        'status_domain::brightness': brightness_body
        'status_domain::mode': mode_body
        'status_domain::firmware': version_body
        'status_domain::hardware': hardware_version_body
        'status_domain::limit': limit_body
        'status_domain::sleep': sleep_body
        'status_domain::wake': wake_body
        'status_domain::timers': timers_body
  - id: checksum
    type: u1
types:
  power_body:
    seq:
      - id: state
        type: u1
      - id: opaque
        size-eos: true
    instances:
      is_on:
        value: state == 1
  limit_body:
    seq:
      - id: value
        type: u1
      - id: opaque
        size-eos: true
    instances:
      is_enabled:
        value: value == 1
  brightness_body:
    seq:
      - id: raw_brightness
        type: u1
      - id: opaque
        size-eos: true
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: opaque
        size-eos: true
  hardware_version_body:
    seq:
      - id: selector
        type: u1
        enum: hardware_selector
      - id: text
        type: strz
        encoding: ASCII
      - id: opaque
        size-eos: true
  mode_body:
    seq:
      - id: mode
        type: u1
        enum: mode_selector
      - id: detail
        size: 16
        type:
          switch-on: mode
          cases:
            'mode_selector::scene': scene_body
            'mode_selector::diy': diy_body
            'mode_selector::static': static_body
            'mode_selector::music': music_body
  static_body:
    seq:
      - id: colour
        type: govee_shared::rgb
      - id: kelvin
        type: u2be
      - id: temperature_colour
        type: govee_shared::rgb
      - id: opaque
        size-eos: true
  scene_body:
    seq:
      - id: scene_id
        type: u2le
      - id: opaque
        size-eos: true
  diy_body:
    seq:
      - id: diy_id
        type: u2le
      - id: opaque
        size-eos: true
  music_body:
    seq:
      - id: music_id
        type: u1
        enum: music_effect
      - id: sensitivity
        type: u1
      - id: colour_mode
        type: u1
      - id: fixed_colour
        type: govee_shared::rgb
        if: colour_mode != 0
      - id: opaque
        size-eos: true
    instances:
      automatic_colour:
        value: colour_mode == 0
  timer_record:
    seq:
      - id: enable_and_action
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
      - id: repeat_mask
        type: u1
    instances:
      is_enabled:
        value: '(enable_and_action & 0x80) != 0'
      turns_on:
        value: '(enable_and_action & 0x01) != 0'
      unknown_flags:
        value: 'enable_and_action & 0x7e'
      is_one_time:
        value: repeat_mask == 0x80
      repeats_every_day:
        value: repeat_mask == 0
      has_explicit_weekdays:
        value: '(repeat_mask & 0x80) != 0 and (repeat_mask & 0x7f) != 0'
      explicit_weekday_mask:
        value: 'repeat_mask & 0x7f'
  timers_body:
    seq:
      - id: selector
        type: u1
      - id: slots
        type: timer_record
        repeat: expr
        repeat-expr: 'selector == 0xff ? 4 : 1'
      - id: opaque
        size-eos: true
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
  status_domain:
    0x01: power
    0x04: brightness
    0x05: mode
    0x06: firmware
    0x07: hardware
    0x0e: limit
    0x11: sleep
    0x12: wake
    0x23: timers
  hardware_selector:
    0x03: primary
  mode_selector:
    0x04: scene
    0x0a: diy
    0x0d: static
    0x0e: music
  music_effect:
    0x00: mode_0
    0x01: mode_1
