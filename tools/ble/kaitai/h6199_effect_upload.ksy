meta:
  id: h6199_effect_upload
  title: Govee H6199 reassembled 0xA3 effect body (decode-only)
  endian: le
  imports:
    - govee_shared
seq:
  - id: header
    contents: [0x01]
  - id: chunk_count
    type: u1
  - id: kind
    type: u1
    enum: body_kind
  - id: content
    type:
      switch-on: kind
      cases:
        'body_kind::builtin_parameters': govee_shared::scene_type1_content
        'body_kind::scene': scene_content
        'body_kind::diy': diy_content
enums:
  body_kind:
    0x01: builtin_parameters
    0x02: scene
    0x04: diy
  effect_family:
    0x00: fade
    0x01: jumping
    0x02: twinkle
    0x03: marquee
    0x04: music
    0x08: chasing
    0x09: rainbow
    0x0a: crossing
types:
  scene_content:
    seq:
      - id: block_count
        type: u1
      - id: blocks
        type: block
        repeat: expr
        repeat-expr: block_count
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  diy_content:
    seq:
      - id: family
        type: u1
        enum: effect_family
      - id: variant
        type: u1
      - id: speed
        type: u1
      - id: palette_len
        type: u1
        valid:
          expr: _ % 3 == 0
      - id: palette
        type: govee_shared::rgb
        repeat: expr
        repeat-expr: palette_len / 3
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  block:
    seq:
      - id: len
        type: u1
      - id: body
        type: govee_shared::effect_layer
        size: len
    instances:
      applied_area:
        value: body.applied_area
      select_type:
        value: body.select_type
      select_param_1:
        value: body.select_param_1
      select_param_2:
        value: body.select_param_2
      layer_flags:
        value: body.layer_flags
      brightness_block_count:
        value: body.brightness_block_count
      brightness_blocks:
        value: body.brightness_blocks
      distribution_direction:
        value: body.direction_distribution
      colour_change_speed:
        value: body.colour_speed
      retention_time:
        value: body.colour_retention
      colour_count:
        value: body.colour_count
      palette:
        value: body.palette
      selected_movement:
        value: body.selected_area_movement.packed
      selected_movement_interval:
        value: body.selected_area_movement.interval
      selected_movement_speed:
        value: body.selected_area_movement.speed
      overall_movement:
        value: body.overall_movement.packed
      overall_movement_interval:
        value: body.overall_movement.interval
      overall_movement_speed:
        value: body.overall_movement.speed
      layer_priority:
        value: body.priority
      excess:
        value: body.excess
      applied_area_width_tenths:
        value: body.applied_area_width_tenths
      applied_area_start_tenths:
        value: body.applied_area_start_tenths
      brightness_is_gradient:
        value: body.brightness_is_gradient
      brightness_scope_low:
        value: body.brightness_blocks[0].brightness_scope_end
      brightness_change_speed:
        value: body.brightness_blocks[0].brightness_speed
      retention_time_brightest:
        value: body.brightness_blocks[0].brightest_retention
      retention_time_darkest:
        value: body.brightness_blocks[0].darkest_retention
      distribution_method:
        value: body.direction_distribution & 0x7f
      direction_is_backward:
        value: body.direction_is_backward
      selected_movement_enabled:
        value: body.selected_area_movement.enabled
      selected_enter_exit_enabled:
        value: body.selected_area_movement.enter_exit_effect
      selected_direction:
        value: body.selected_area_movement.direction
