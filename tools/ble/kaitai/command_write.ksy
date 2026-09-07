meta:
  id: command_write
  title: Govee H617A "33" command-write envelope (decode-only)
  endian: le
  imports:
    - govee_shared
    - govee_common
doc: |
  H617A 20-byte command frame. The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command_op
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_cmd
        'command_op::brightness': brightness_cmd
        'command_op::multi': multi_cmd
        'command_op::multi_effect': multi_effect_cmd
        'command_op::dreamview': dreamview_cmd
        'command_op::display_setting': display_setting_cmd
  - id: checksum
    type: u1
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x60: dreamview
    0xa3: multi_effect
    0xa9: display_setting
  dreamview_sub:
    0x01: switch_on_off
    0x03: device_brightness
    0x04: brightness_unite
    # `33 60 05 {index, connect}` -- take ONE sub-device off the sync centre's BLE link, or give
    # it back. Named from SubDeviceConnectController: getCommandType() is 5 and q() emits
    # {g, f} while the call site builds it as (z ? 1 : 0, i), so g is the member INDEX and f the
    # flag -- index first on the wire. The capture agrees independently: writing {slot, 0} drives
    # that slot's `aa 60 05` byte to 0, and {slot, 1} drives it 1 then 2.
    0x05: sub_device_connect
    0x09: saturation
    0x0a: get_color_mode
    0x0b: sound_effects
    0x0d: delete_group
  display_setting:
    0x06: white_balance
    0x0a: black_screen_detection
    0x0b: black_border_removal
    0x10: ai_filter
    0x11: hdr_effect
  multi_sub:
    0x00: video
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
  multi_effect_cmd:
    doc: >
      Boolean gradual-change register. The app writes false as the prologue to
      per-segment paint batches and labels the switch as gradual colour change. True is
      accepted, read back and retained across power. H617A goods type 73 is explicitly
      marked as not supporting gradual change, and paired native-scene, segment-paint and
      static-colour comparisons produced no visible difference. The raw state is retained
      as an unsupported device register rather than exposed as a capability.
    seq:
      - id: flag
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  power_cmd:
    seq:
      - id: is_on
        type: u1
  brightness_cmd:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
  multi_cmd:
    seq:
      - id: sub
        type: u1
        enum: multi_sub
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'multi_sub::video': video_body_h66a0
            'multi_sub::scene': scene_activate
            'multi_sub::diy': govee_common::diy_selector
            'multi_sub::music': govee_common::music_selector
            'multi_sub::static': static_cmd
  scene_activate:
    seq:
      - id: code
        type: u2le
      - id: scene_type
        type: u1
  segment_mask:
    seq:
      - id: bits
        type: u2le
  static_cmd:
    seq:
      - id: static_sub
        type: u1
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            0x01: static_color
            0x02: static_brightness
            0x03: static_brightness_all
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
  static_brightness:
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
      - id: mask
        type: segment_mask
  static_brightness_all:
    seq:
      - id: segment_percent
        type: u1
        valid:
          max: 100
        repeat: eos
  dreamview_cmd:
    doc: |
      DreamView, which the app calls "Feast" internally.

      Every controller extends AbsSingleFeastController, whose u() returns (byte) 96 = 0x60,
      and whose matcher is `proType == bArr[0] && 0x60 == bArr[1] && commandType == bArr[2]`.
      So a frame is `<33|aa> 60 <sub> <payload>` and the sub-command IS the controller's
      getCommandType(). Names below come from those classes, cross-checked against a capture
      of the app creating, configuring, toggling and deleting a group.

      DESTRUCTIVE sub-commands are deliberately absent from the enum rather than merely
      unimplemented: 0x06 DeviceResetController, 0x07 SubDeviceClearController and
      0x0d MovieDeleteController. A group's membership and per-member Area Config are written
      by a 0xa3 upload and never read back, so a group deleted from here cannot be rebuilt
      from here. Adding them needs a deliberate decision, not a passing one.

      0x0c is not a controller at all: a live read returned 01 34 3b 01 01 01 37, every field
      of which appears in the other registers. It is a read-only digest.
    seq:
      - id: sub
        type: u1
        enum: dreamview_sub
      - id: payload
        size-eos: true
        type:
          switch-on: sub
          cases:
            'dreamview_sub::switch_on_off': dreamview_switch
            'dreamview_sub::device_brightness': dreamview_pair
            'dreamview_sub::brightness_unite': dreamview_single
            'dreamview_sub::sub_device_connect': dreamview_pair
            'dreamview_sub::saturation': dreamview_single
            'dreamview_sub::get_color_mode': dreamview_pair
            'dreamview_sub::sound_effects': dreamview_pair
            'dreamview_sub::delete_group': dreamview_single
  dreamview_switch:
    doc: MovieOpenControllerV2 builds {on, 1} -- the trailing 1 is part of the payload.
    seq:
      - id: is_on
        type: u1
        valid:
          max: 1
      - id: trailer
        contents: [1]
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  dreamview_single:
    seq:
      - id: value
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  dreamview_pair:
    doc: |
      Two bytes, meaning per sub-command:
        device_brightness  {level 0..100, member index}
        get_color_mode     {mode, flag}   -- the All/Part choice
        sound_effects      {on, softness 0..100}
    seq:
      - id: first
        type: u1
      - id: second
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  display_setting_cmd:
    doc: |
      Write to one 0xa9 register: the sub-command, a value count, and that many values --
      the same shape the read answers in (status_reply::display_setting_body).

      Typed payloads require matching write and read-back evidence. Every other register
      stays raw.
    seq:
      - id: setting
        type: u1
        enum: display_setting
      - id: len
        type: u1
      - id: payload
        size: len
        type:
          switch-on: setting
          cases:
            'display_setting::white_balance': scalar_white_balance_payload
            'display_setting::black_screen_detection': black_screen_payload
            'display_setting::black_border_removal': black_border_removal_payload
            'display_setting::hdr_effect': hdr_effect_payload
            'display_setting::ai_filter': ai_filter_payload
  scalar_white_balance_payload:
    seq:
      - id: value
        type: u1
  ai_filter_payload:
    doc: |
      The app's AI Filter toggle. `33 a9 10 0f <on> <8 zero bytes> <timestamp>`, and the read
      answers in the same shape.

      Captured from the vendor app on 2026-08-26 turning it on and then off, the two frames
      differing only in the enable byte:

        33 a9 10 0f 01 00*8 ea 07 08 1a 08 21
        33 a9 10 0f 00 00*8 ea 07 08 1a 08 21

      The eight bytes between the enable and timestamp are selected-filter parameters, not
      padding. A writer must read and preserve them because their meanings are unavailable
      from the device. The tail is a UTC wall-clock stamp.
    seq:
      - id: is_on
        type: u1
        valid:
          max: 1
      - id: params
        size: 8
      - id: year
        type: u2
      - id: month
        type: u1
      - id: day
        type: u1
      - id: hour
        type: u1
      - id: minute
        type: u1
  black_screen_payload:
    doc: |
      Blank-screen detection: an enable byte and five more the app also writes.

      The five bytes after the enable ARE identified, as of 2026-08-27: they are the same layout
      the H6199 uses (h6199_command_write::blank_screen_payload) -- `detection` then two
      little-endian u16 durations in seconds. Confirmed against the capture, where the owner had
      set 22 minutes and the register read `02 17 00 28 05`: detection 2 (same tone), 23 s, and
      0x0528 = 1320 s = 22 minutes exactly.

      They stay `opaque` HERE only because this frame's writer preserves them wholesale;
      coordinator.video_blank_screen_config is what decodes and edits them. A writer that does
      not understand them must still READ THEM BACK AND PRESERVE THEM rather than invent values.
    seq:
      - id: is_on
        type: u1
        valid:
          max: 1
      - id: opaque
        type: u1
        repeat: expr
        repeat-expr: 5
  black_border_removal_payload:
    seq:
      - id: is_on
        type: u1
        valid:
          max: 1
  hdr_effect_payload:
    doc: |
      HDR contrast: an enable and a GEAR INDEX, not a percentage.

      Captured writes and replies establish the field order. The range is 1..4: labelled
      device states reported `02 01 01` through `02 01 04`.
    seq:
      - id: is_on
        type: u1
        valid:
          max: 1
      - id: gear
        type: u1
        valid:
          min: 1
          max: 4
  video_body_h66a0:
    doc: |
      Video mode on an H66A0: `33 05 00` followed by six bytes. An `aa 05` read in video mode
      returns the same six fields after the mode byte, so read and write share this layout.

        game_mode       0 = Movie, 1 = Game.
        picture_preset  0x08 Vivid, 0x09 Solid, 0x0a Smooth, 0x0b Delicate.
        saturation      0..100. Read back as 0x3e = 62 against a slider showing 62%.
        sound_effects   0/1.
        reserved        Unidentified. Preserve the reported value.
        sound_effects_softness
                        0..100.

      Relative brightness is carried by the separate 0xae command.
    seq:
      - id: game_mode
        type: u1
        valid:
          max: 1
      - id: picture_preset
        type: u1
      - id: saturation
        type: u1
        valid:
          max: 100
      - id: sound_effects
        type: u1
        valid:
          max: 1
      - id: reserved
        type: u1
      - id: sound_effects_softness
        type: u1
        valid:
          max: 100
