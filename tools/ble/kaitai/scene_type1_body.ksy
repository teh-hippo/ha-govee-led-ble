meta:
  id: scene_type1_body
  title: Govee H617A reassembled type-1 scene body
  endian: le
  imports:
    - govee_common
    - govee_shared
seq:
  - id: header
    type: govee_common::a3_header
  - id: scene_type
    type: u1
    valid: 1
  - id: content
    type: govee_shared::scene_type1_content
instances:
  config:
    value: content.config
  step_count:
    value: content.step_count
  steps:
    value: content.steps
  palette_count:
    value: content.palette_count
  palette:
    value: content.palette
  padding:
    value: content.padding
  colour_stride:
    value: content.colour_stride
  layout:
    value: content.layout
  brightness_flag:
    value: content.brightness_flag
