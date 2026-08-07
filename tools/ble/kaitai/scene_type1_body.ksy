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
  num_steps:
    value: content.num_steps
  steps:
    value: content.steps
  num_palette:
    value: content.num_palette
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
