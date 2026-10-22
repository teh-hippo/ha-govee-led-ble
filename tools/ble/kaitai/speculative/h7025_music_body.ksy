meta:
  id: h7025_music_body
  title: Govee H7025 music palettes and style-specific tails
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h617a_control_payload
doc: |
  SPECULATIVE H7025, issue #148.
  The reporter's working snapshot replays corroborate the IDs and tail prefixes
  selected by Android 7.6.01 H7025 music authoring.  This is not an H617A body alias.
  Its exact caller supplies Hopping ID 48, independently of the shared Hopping
  builder's default ID 5E, and emits background RGB, brightness, and two zero
  bytes.  Rolling and Separation similarly emit direction and two zero bytes,
  and Sway and Twinkle emit three zero bytes.  These bytes belong to the
  serialised body, but their firmware meaning remains unknown.
  Flow emits direction, group count, and ICs per group.  Star emits background
  RGB and a field named distance; the reported brightness interpretation of
  that byte is unconfirmed.  Piano and Day/Night reuse the named shared tails
  with exact-H7025 defaults and editor permissions.  Palette counts do not
  establish physical IC count.
  The app's multi-packet uploader emits 15 initial stream bytes and up to 17
  final bytes.  The reporter's eight-byte final threshold remains a separate,
  unresolved snapshot/firmware observation; it does not change shared framing.
  Unresolved: revision differences, raw snapshot sequences, all field bounds
  on hardware, rendering, and the necessity of body zeros versus frame padding.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: music_mode
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
  - id: tail
    size: tail_len
    type:
      switch-on: mode
      cases:
        'music_mode::sway': colour_only_tail
        'music_mode::twinkle': colour_only_tail
        'music_mode::flow': flow_tail
        'music_mode::star': star_tail
        'music_mode::hopping': hopping_tail
        'music_mode::rolling': direction_tail
        'music_mode::separation': direction_tail
        'music_mode::piano_keys': h617a_control_payload::piano_keys_tail
        'music_mode::day_and_night': h617a_control_payload::day_and_night_tail
  - id: padding
    size-eos: true
instances:
  tail_len:
    value: >-
      mode == music_mode::hopping ? 6 :
      mode == music_mode::star ? 4 :
      mode == music_mode::piano_keys ? 5 : 3
enums:
  music_mode:
    0x8e: sway
    0x59: flow
    0x98: star
    0x8f: twinkle
    0x48: hopping
    0x5a: rolling
    0x37: day_and_night
    0x34: piano_keys
    0x5d: separation
  direction:
    6: left
    7: right
    8: spread
    9: gather
  flow_direction:
    0: clockwise
    1: counterclockwise
types:
  colour_only_tail:
    seq:
      - id: unknown
        size: 3
  flow_tail:
    seq:
      - id: direction
        type: u1
        enum: flow_direction
      - id: group_count
        type: u1
      - id: ics_per_group
        type: u1
  star_tail:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: distance
        type: u1
  hopping_tail:
    seq:
      - id: background
        type: govee_shared::rgb
      - id: rel_brightness
        type: u1
      - id: unknown
        size: 2
  direction_tail:
    seq:
      - id: direction
        type: u1
        enum: direction
      - id: unknown
        size: 2
