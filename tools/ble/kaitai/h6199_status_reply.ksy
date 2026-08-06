meta:
  id: h6199_status_reply
  title: Govee H6199 "aa" status-reply envelope (decode-only)
  endian: le
doc: |
  H6199 light-to-phone status notification, modelled independently from the
  H617A status grammar. This root begins with the attributable iPhone capture
  h6199-aa40.pcap and deliberately imports no shared Govee types.

  Domains 0x06, 0x07, 0x20 and 0x21 are separated by bytes in one connect burst:
  firmware, hardware and two further version strings. Domain 0x14 is omitted
  because its captured body contains the real device address, which is rig
  identity and does not belong in a committed fixture.

  THE TWO EXTRA VERSIONS BELONG WITH THE HARDWARE ONE, which is more than the bytes
  alone say and less than a name. The app's Device Settings page shows a single
  "Hardware Version" row reading "3.02.01" and then "1.03.00/1.00.33", and those are
  exactly the 0x07, 0x20 and 0x21 replies captured seconds earlier, string for
  string. So the pair is hardware-related and is not a second firmware, which is the
  reading their position next to 0x06 would otherwise invite.

  They keep neutral names anyway. Being displayed together rules out what they are
  NOT; it does not say which component each one belongs to, and inventing that from a
  slash in a settings row would be exactly the kind of guess the neutral name exists
  to avoid. Settle it on a device whose parts have distinguishable versions.

  Opening that page put nothing on the wire, so it is a display of what the connect
  burst already fetched rather than a reason for the light to be asked anything.

  Domain 0x01 is modelled as well and is much the weakest of them, because its captured
  reply is byte-identical to the query that drew it. See power_body for what that leaves
  unsettled.
seq:
  - id: header
    contents: [0xaa]
    doc: '[CONFIRMED_LIVE] H6199 status header at frame offset 0'
  - id: domain
    type: u1
    enum: status_domain
    doc: '[CONFIRMED_LIVE] H6199 status register at frame offset 1'
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'status_domain::power': power_body
        'status_domain::brightness': brightness_body
        'status_domain::firmware': version_body
        'status_domain::hardware': hardware_version_body
        'status_domain::subordinate_20': version_body
        'status_domain::subordinate_21': version_body
        'status_domain::colour_mode': colour_mode_body
        'status_domain::display_setting': display_setting_body
        'status_domain::relative_brightness': relative_brightness_body
        'status_domain::segments': segment_group_body
    doc: '[CONFIRMED_LIVE] H6199 status body at frame offsets 2..18; unmatched registers remain raw'
  - id: checksum
    type: u1
    doc: '[CONFIRMED_LIVE] raw XOR checksum byte at frame offset 19; validated by the fixture runner'
enums:
  status_domain:
    0x01: power
    0x04: brightness
    0x06: firmware
    0x07: hardware
    0x05: colour_mode
    0x20: subordinate_20
    0x21: subordinate_21
    0xa5: segments
    0xa9: display_setting
    0xae: relative_brightness
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
  mode_sel:
    0x00: video
    0x04: scene
    0x13: music
    0x15: static_colour
  video_source:
    0x00: movie
    0x01: game
  video_region:
    0x00: part
    0x01: all
types:
  rgb:
    seq:
      - id: red
        type: u1
        doc: '[CONFIRMED_LIVE] red channel'
      - id: green
        type: u1
        doc: '[CONFIRMED_LIVE] green channel'
      - id: blue
        type: u1
        doc: '[CONFIRMED_LIVE] blue channel'
  display_setting_body:
    seq:
      - id: setting
        type: u1
        enum: display_setting
        doc: '[CONFIRMED_LIVE] display-setting selector echoed at frame offset 2'
      - id: len
        type: u1
        doc: |
          [CONFIRMED_LIVE] setting payload length at frame offset 3, captured as six for both
          white balance and blank screen and consuming exactly the bytes before zero padding.
      - id: payload
        size: len
        type:
          switch-on: setting
          cases:
            'display_setting::white_balance': white_balance_state
            'display_setting::blank_screen': blank_screen_state
        doc: '[CONFIRMED_LIVE] setting-specific state payload at frame offset 4'
      - id: opaque_tail
        size-eos: true
        doc: '[CONFIRMED_LIVE] zero padding after the declared display-setting payload'
  white_balance_state:
    seq:
      - id: reset_flag
        type: u1
        doc: |
          [CONFIRMED_LIVE] first white-balance triple's leading byte, captured as 0x01 in
          every reply and left unnamed because it never varied.
      - id: reset_red
        type: u1
        doc: |
          [CONFIRMED_LIVE] red gain of the device's reset reference. It stayed 16 before
          Reset, after Reset and after moving the manual strip to warm.
      - id: reset_blue
        type: u1
        doc: |
          [CONFIRMED_LIVE] blue gain of the device's reset reference. It stayed 3 before
          Reset, after Reset and after moving the manual strip to warm.
      - id: current_flag
        type: u1
        doc: |
          [CONFIRMED_LIVE] current white-balance triple's leading byte, captured as 0x01 in
          every reply and left unnamed because it never varied.
      - id: current_red
        type: u1
        doc: |
          [CONFIRMED_LIVE] current red gain. It read 13 before Reset, 16 after Reset and 21
          after moving the manual strip to its warm endpoint, while reset_red stayed 16.
      - id: current_blue
        type: u1
        doc: |
          [CONFIRMED_LIVE] current blue gain. It read 3 before and after Reset, then 5 at
          the warm endpoint, while reset_blue stayed 3.
  blank_screen_state:
    seq:
      - id: is_enabled
        type: u1
        doc: |
          [CONFIRMED_LIVE] blank-screen state at frame offset 4. Captured as zero while the
          app's switch displayed off and one after it was enabled, with the remaining bytes
          unchanged.
      - id: opaque_tail
        size: 5
        doc: '[CONFIRMED_LIVE] five state bytes mirrored from the blank-screen write, still unnamed'
  relative_brightness_body:
    seq:
      - id: selector
        contents: [0x01]
        doc: '[CONFIRMED_LIVE] relative-brightness reply selector at frame offset 2'
      - id: edge_count
        contents: [0x04]
        doc: '[CONFIRMED_LIVE] four edge values follow, at frame offset 3'
      - id: left_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] left edge percentage at frame offset 4. An asymmetric reply carried
          51, 32, 71 and 91 after those exact values were written to left, top, right and bottom.
      - id: top_percent
        type: u1
        doc: '[CONFIRMED_LIVE] top edge percentage at frame offset 5; see left_percent'
      - id: right_percent
        type: u1
        doc: '[CONFIRMED_LIVE] right edge percentage at frame offset 6; see left_percent'
      - id: bottom_percent
        type: u1
        doc: '[CONFIRMED_LIVE] bottom edge percentage at frame offset 7; see left_percent'
      - id: opaque_tail
        size-eos: true
        doc: '[CONFIRMED_LIVE] remaining relative-brightness reply bytes, captured as zero'
  colour_mode_body:
    doc: |
      What the light says it is currently showing. This is the read side of the 0x05 mode
      register, and it answers a question the integration had been assuming: the H6199 DOES
      reply to an aa 05 query. Four replies were captured across four sessions, one per mode.

      MODELLED SEPARATELY FROM THE WRITE BODIES RATHER THAN IMPORTED, even though both are
      this same model and an import would be allowed. The two are not the same shape: the
      write's scene body carries a classifier byte at the position where this reply carries
      zero. Importing would assert a sameness these bytes contradict, and would then be wrong
      silently rather than loudly.

      Read-side fields are named only where a write in the SAME session pins them. Where the
      layout merely resembles the write, the doc says so.
    seq:
      - id: mode
        type: u1
        enum: mode_sel
        doc: |
          [CONFIRMED_LIVE] which mode the light reports, at frame offset 2. Captured as 0x15
          static colour, 0x13 music, 0x00 video and 0x04 scene, in four sessions in which the
          app had put the light into exactly that mode. It is the same set of values the
          write side selects on, which is the device confirming that enum from the other
          direction rather than us reading our own encoder back.
      - id: detail
        size: 16
        doc: '[CONFIRMED_LIVE] the mode payload at frame offsets 3..18; modes without an isolated body remain raw'
        type:
          switch-on: mode
          cases:
            'mode_sel::video': video_state
            'mode_sel::music': music_state
            'mode_sel::scene': scene_state
  music_state:
    seq:
      - id: mode
        type: u1
        doc: |
          [CONFIRMED_LIVE] the music mode, at frame offset 3, captured as 0x05. The write that
          set it in the same session carried 0x05 in the same position for the tile the app
          labels Energic, so the reply echoes the selection rather than reporting an index of
          its own.
      - id: sensitivity
        type: u1
        doc: |
          [CONFIRMED_LIVE] the music sensitivity, at frame offset 4, captured as 0x63. The
          same session's write carried 0x63 for a slider left near, but not at, the top of its
          travel: the maximum was later measured at 100.

          This is the read-back the write-side doc once proposed as the way to settle that
          byte, and it arrives from a genuinely independent direction: the light is reporting
          the value, not our encoder repeating it. The two agree.
      - id: is_calm
        type: u1
        doc: |
          [CONFIRMED_LIVE] reactivity profile at frame offset 5. Fixed-red and fixed-blue
          replies both carried zero after Dynamic was selected, matching the write layout.
      - id: has_fixed_colour
        type: u1
        doc: |
          [CONFIRMED_LIVE] fixed-colour flag at frame offset 6. Captured as one in fixed-red
          and fixed-blue replies, matching the writes that established those colours.
      - id: fixed_colour
        type: rgb
        doc: |
          [CONFIRMED_LIVE] fixed music colour at frame offsets 7..9. Captured as ff 00 00
          after selecting red and 00 00 ff after selecting blue, then read independently
          during a fresh connection burst.
      - id: opaque_tail
        size: 9
        doc: '[CONFIRMED_LIVE] remaining bytes at frame offsets 10..18, captured as an opaque all-zero window'
  video_state:
    doc: |
      The current video settings, independently modelled from the write body. A retained
      2026-08-05 capture contains a 33 05 00 write for Part, Game, saturation 20, sound
      enabled and softness 12, followed later in the same session by an aa 05 reply carrying
      the same five values in the same positions. Fresh-connection replies additionally
      carry All/Movie and All/Game at 100/off/100, separating both enums and both percentage
      ranges from constants.
    seq:
      - id: region
        type: u1
        enum: video_region
        doc: '[CONFIRMED_LIVE] capture region at frame offset 3; Part 0 and All 1 both read back, with the Part value matching the same-session write'
      - id: source
        type: u1
        enum: video_source
        doc: '[CONFIRMED_LIVE] picture profile at frame offset 4; Movie 0 and Game 1 both read back, with Game matching the same-session write'
      - id: saturation
        type: u1
        doc: '[CONFIRMED_LIVE] direct saturation percentage at frame offset 5; 20 and 100 read back, with 20 matching the same-session write'
      - id: sound_effects
        type: u1
        doc: '[CONFIRMED_LIVE] sound-effects state at frame offset 6; zero and one read back, with one matching the same-session write'
      - id: softness
        type: u1
        doc: '[CONFIRMED_LIVE] direct softness percentage at frame offset 7; 12 and 100 read back, with 12 matching the same-session write'
      - id: opaque_tail
        size: 11
        doc: '[CONFIRMED_LIVE] remaining video-state bytes at frame offsets 8..18, captured as an opaque all-zero window'
  scene_state:
    seq:
      - id: scene_id
        type: u2le
        doc: |
          [CONFIRMED_LIVE] the scene the light reports, at frame offsets 3..4, in the same
          two-byte little-endian form the write uses. Captured as 0x2715, which is exactly
          the id the app had written moments earlier in the same session.

          THE WRITE'S CLASSIFIER BYTE IS NOT ECHOED. That write carried a 2 in the next
          position and this reply carries 0. What that shows is only that the byte is not part
          of what the light reports back; it does not say what the byte means, and an earlier
          version of this doc read it as evidence for a meaning that has since been retracted.
          See h6199_command_write::scene_body::scene_class, which now records three readings
          and no conclusion.
      - id: opaque_tail
        size: 14
        doc: '[CONFIRMED_LIVE] remaining bytes at frame offsets 5..18, captured as an opaque all-zero window'
  power_body:
    seq:
      - id: is_on
        type: u1
        doc: |
          [CONFIRMED_LIVE] power state at frame offset 2. Captured as zero while off and one
          from fresh device replies while on, so it is not an echo of the all-zero query.
      - id: opaque_tail
        size: 16
        doc: '[CONFIRMED_LIVE] remaining H6199 power-reply bytes, captured as an opaque all-zero window'
  brightness_body:
    seq:
      - id: percent
        type: u1
        doc: '[CONFIRMED_LIVE] direct whole-strip brightness percentage at frame offset 2; retained replies include 3 and 24 after the device was set to those levels'
      - id: opaque_tail
        size: 16
        doc: '[CONFIRMED_LIVE] remaining H6199 brightness-reply bytes, captured as an opaque all-zero window'
  segment_record:
    seq:
      - id: brightness_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] direct per-segment brightness. H6199 trials changed one segment
          to 17, segments 2 and 4 to 37, and every segment to 73; each reply reported the
          requested value at the corresponding position.
      - id: colour
        type: rgb
        doc: '[CONFIRMED_LIVE] segment RGB, retained while brightness alone was changed'
  segment_group_body:
    seq:
      - id: group
        type: u1
        doc: |
          [CONFIRMED_LIVE] one-based group number. Groups 1 to 3 carry four segment records;
          group 4 carries the final three records followed by a four-byte device trailer.
      - id: segments
        type: segment_record
        repeat: expr
        repeat-expr: 'group == 4 ? 3 : 4'
        doc: '[CONFIRMED_LIVE] consecutive segment states for this group'
      - id: group4_tail
        size: 4
        if: group == 4
        doc: '[CONFIRMED_LIVE] final group trailer, left opaque because no controlled comparison isolates its fields'
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
        doc: '[CONFIRMED_LIVE] NUL-terminated H6199 version string'
      - id: opaque_tail
        size-eos: true
        doc: '[CONFIRMED_LIVE] remaining bytes after the H6199 version string, captured as an opaque all-zero window'
  hardware_version_body:
    seq:
      - id: prefix
        contents: [0x03]
        doc: '[CONFIRMED_LIVE] H6199 hardware-version selector prefix at frame offset 2'
      - id: text
        type: strz
        encoding: ASCII
        doc: '[CONFIRMED_LIVE] NUL-terminated H6199 hardware version string'
      - id: opaque_tail
        size-eos: true
        doc: '[CONFIRMED_LIVE] remaining bytes after the H6199 hardware version, captured as an opaque all-zero window'
