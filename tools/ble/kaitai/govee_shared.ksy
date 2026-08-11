meta:
  id: govee_shared
  title: Shared Govee BLE wire datatypes
  endian: le
types:
  rgb:
    seq:
      - id: red
        type: u1
      - id: green
        type: u1
      - id: blue
        type: u1
    instances:
      r:
        value: red
      g:
        value: green
      b:
        value: blue
  brightness_block:
    seq:
      - id: brightness_scope_start
        type: u1
      - id: brightness_scope_end
        type: u1
      - id: brightness_order
        type: u1
        enum: brightness_order
      - id: brightness_speed
        type: u1
      - id: brightest_retention
        type: u1
      - id: darkest_retention
        type: u1
    instances:
      scope_high:
        value: brightness_scope_start
      scope_low:
        value: brightness_scope_end
      order:
        value: brightness_order
      change_speed:
        value: brightness_speed
      retention_brightest:
        value: brightest_retention
      retention_darkest:
        value: darkest_retention
  movement:
    seq:
      - id: packed
        type: u1
      - id: interval
        type: u1
      - id: speed
        type: u1
    instances:
      enabled:
        value: '(packed & 0x10) != 0'
      enter_exit_effect:
        value: '(packed & 0x04) != 0'
      direction:
        value: 'packed & 0x03'
      unknown_flags:
        value: 'packed & 0xe8'
  effect_layer:
    seq:
      - id: applied_area
        type: u1
      - id: select_type
        type: u1
        enum: select_type
      - id: select_param_1
        type: u1
      - id: select_param_2
        type: u1
      - id: layer_flags
        type: u1
      - id: num_brightness_blocks
        type: u1
      - id: brightness_blocks
        type: brightness_block
        repeat: expr
        repeat-expr: num_brightness_blocks
      - id: direction_distribution
        type: u1
      - id: colour_speed
        type: u1
      - id: colour_retention
        type: u1
      - id: num_palette
        type: u1
      - id: palette
        type: rgb
        repeat: expr
        repeat-expr: num_palette
      - id: selected_area_movement
        type: movement
      - id: overall_movement
        type: movement
      - id: priority
        type: u1
      - id: excess
        size-eos: true
    instances:
      applied_area_width_tenths:
        value: '(applied_area & 0xf0) >> 4'
      applied_area_start_tenths:
        value: 'applied_area & 0x0f'
      direction_is_backward:
        value: '(direction_distribution & 0x80) != 0'
      distribution_method:
        value: 'direction_distribution & 0x7f'
      brightness_is_gradient:
        value: '(layer_flags & 0x02) != 0'
      unknown_flags:
        value: 'layer_flags & 0xfd'
  scene_type1_content:
    seq:
      - id: config
        type: u1
        valid:
          expr: 'layout <= 1 and colour_stride == 3'
      - id: num_steps
        type: u1
      - id: steps
        type:
          switch-on: layout
          cases:
            0: scene_type1_step
            1: scene_type1_step_inline_colour
        repeat: expr
        repeat-expr: num_steps
      - id: num_palette
        type: u1
        if: layout == 0
      - id: palette
        type: rgb
        repeat: expr
        repeat-expr: num_palette
        if: layout == 0
      - id: padding
        type: u1
        valid: 0
        repeat: eos
    instances:
      colour_stride:
        value: 'config & 0x07'
      layout:
        value: '(config >> 4) & 0x07'
      brightness_flag:
        value: '(config & 0x80) != 0'
  scene_type1_step:
    seq:
      - id: colour
        type: rgb
      - id: value
        type: u2
  scene_type1_step_inline_colour:
    seq:
      - id: param
        type: scene_type1_step
      - id: colour
        type: rgb
enums:
  brightness_order:
    0: brightest_darkest
    1: brightest_darkest_brightest
    2: darkest_brightest
    3: darkest_brightest_darkest
  select_type:
    0: segment
    1: select_ic_continuously
    2: select_ic_randomly
    3: customize_segment
