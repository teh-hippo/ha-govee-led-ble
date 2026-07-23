meta:
  id: status_reply
  title: Govee H617A "aa" status-reply envelope (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  Light -> phone status notification, 20 bytes: aa <domain> <17-byte body> <xor>.
  byte[19] is the XOR of bytes[0..18]; opaque here and validated host-side
  (Kaitai has no fold/reduce). One envelope for the whole aa read-back family,
  per-domain bodies below, including colour-mode (domain 0x05).
  Re-verified byte-exact against captured replies (see roundtrip_status.py);
  captures are ground truth. Field meanings cross-checked against
  protocol.split_status_frame / parse_color_mode_response / parse_fw_version /
  parse_hw_version.
  Observed H617A domains NOT modelled here (fall back to raw): 0x04 group /
  segment count (reply 0x05, 0x64 seen); 0x14; 0x40 IC / segment count (query
  aa 40 00 -> reply aa 40 00 0f = 15 segments); 0xa3 multi-frame state read-back
  (x178). Queued for on-phone query->reply correlation (validation_backlog
  aa-readback-gaps). The sleep-timer (0x11) and wake-timer (0x12) read-backs are
  now modelled below, sharing govee_common.sleep_timer / wake_timer with the 0x11 /
  0x12 command writes (write<->read-back byte-identical, live 2026-07-23). The
  colour-mode DIY (0x0a) and music (0x13) read-backs likewise share
  govee_common::diy_selector / music_selector with the matching 33 05 writes.
  Every field carries one evidence tag in its doc: [CONFIRMED_LIVE] proven by a
  round-tripped capture; [INFERRED] reasoned but the value is not isolated in a
  capture; [INHERITED] modelled from the write-side/docs with no confirming
  capture (the pessimistic default).
seq:
  - id: header
    contents: [0xaa]
    doc: '[CONFIRMED_LIVE] status header, raw 0xaa'
  - id: domain
    type: u1
    enum: aa_domain
    doc: '[CONFIRMED_LIVE] domain selector byte (frame offset 1)'
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'aa_domain::power': power_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::segments': segments_body
        'aa_domain::timer': timer_body
        'aa_domain::sleep_timer': govee_common::sleep_timer
        'aa_domain::wake_timer': govee_common::wake_timer
    doc: '[CONFIRMED_LIVE] bytes 2..18, interpreted per domain (unmatched domains fall back to raw)'
  - id: checksum
    type: u1
    doc: '[CONFIRMED_LIVE] raw XOR of bytes[0..18]; opaque, host-validated'
enums:
  aa_domain:
    0x01: power
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x11: sleep_timer
    0x12: wake_timer
    0x23: timer
    0xa5: segments
  color_mode:
    0x15: static
    0x04: scene
    0x0a: diy
    0x00: video
    0x13: music
types:
  power_body:
    doc: |
      domain 0x01 power read-back: is_on then zero padding. NOTE a second, longer
      aa 01 form exists that this grammar does NOT model and will reject on the
      padding assertion: aa 01 0c 00 01 00 27 11 24 <b9> 17 <b11> 01 00 00 00 ...
      (x4 H617A: color-walkthrough, workshop-minimum-validity, video-mode,
      scene-natural; constants 0x0c/27 11 24/17/01, bytes 9+11 vary). Its layout and
      trigger are unknown; capture-correlate on-phone before modelling it.
    seq:
      - id: is_on
        type: u1
        doc: '[CONFIRMED_LIVE] raw power state, 0x00 off / 0x01 on'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  colormode_body:
    doc: |
      domain 0x05 colour-mode read-back. The first body byte selects the mode; the
      following bytes mirror the matching write body. Cross-checked against
      protocol.parse_color_mode_response. All five mode selectors are seen live;
      only the static sub 0x01/0x02 read-back branches lack a capture.
    seq:
      - id: mode
        type: u1
        enum: color_mode
        doc: '[CONFIRMED_LIVE] raw colour-mode selector (frame offset 2)'
      - id: mode_body
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::static': cm_static
            'color_mode::scene': cm_scene
            'color_mode::diy': govee_common::diy_selector
            'color_mode::video': cm_video
            'color_mode::music': govee_common::music_selector
        doc: '[CONFIRMED_LIVE] the 16 bytes at frame offsets 3..18, interpreted per mode'
  cm_static:
    doc: |
      mode 0x15 static read-back. Live H617A 2026-07-22 (driven over HA on
      light.cupboard_skirt): after setting a static RGB colour AND after setting a
      colour temperature, the reply is byte-identical -- aa 05 15 00 then an all-zero
      payload. The device echoes only the mode and sub 0x00; it never returns the
      colour, kelvin or brightness. Those stay write-only (see command_write.ksy
      static_color, whose sub 0x01 carries rgb and 0x02 a white-brightness percent)
      and the integration keeps them optimistically. The write-side 0x01/0x02
      sub-selectors are never seen in a read-back, so no read-back sub-branch is
      modelled; any non-zero payload trips the zero assertion below and must be
      captured before it is modelled.
    seq:
      - id: sub
        type: u1
        doc: '[CONFIRMED_LIVE] static sub-selector at frame offset 3; always 0x00 in H617A read-backs (an RGB set and a CT set both read back 0x00)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] all-zero payload within the 16-byte mode window; the set colour/kelvin/brightness is never echoed'
  cm_scene:
    doc: mode 0x04. Scene effect id, little-endian, at frame offset 3+.
    seq:
      - id: scene_id
        type: u2le
        doc: '[CONFIRMED_LIVE] scene effect id (little-endian) at frame offset 3'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte mode window; grammar-enforced all-zero'
  cm_video:
    doc: mode 0x00 (H6199). Region/mode/saturation/sound/softness at offsets 3..7.
    seq:
      - id: full_screen
        type: u1
        doc: '[CONFIRMED_LIVE] region 1=all / 0=part (frame offset 3)'
      - id: game_mode
        type: u1
        doc: '[CONFIRMED_LIVE] game-mode flag (frame offset 4)'
      - id: saturation
        type: u1
        doc: '[CONFIRMED_LIVE] saturation 0..100 (frame offset 5)'
      - id: sound_effects
        type: u1
        doc: '[CONFIRMED_LIVE] sound-effects flag (frame offset 6)'
      - id: softness
        type: u1
        doc: '[CONFIRMED_LIVE] sound-effects softness (frame offset 7)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte mode window; grammar-enforced all-zero'
  version_body:
    doc: firmware version, ASCII, NUL-terminated (e.g. "3.02.24")
    seq:
      - id: text
        type: strz
        encoding: ASCII
        doc: '[CONFIRMED_LIVE] firmware version ASCII string, NUL-terminated'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  hw_version_body:
    doc: hardware version; a 0x03 prefix then ASCII NUL-terminated (e.g. "3.01.01")
    seq:
      - id: prefix
        contents: [0x03]
        doc: '[CONFIRMED_LIVE] raw 0x03 selector prefix'
      - id: text
        type: strz
        encoding: ASCII
        doc: '[CONFIRMED_LIVE] hardware version ASCII string, NUL-terminated'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  segments_body:
    doc: group id then three segments of <brightness> <R> <G> <B> (aa a5 read-back)
    seq:
      - id: group
        type: u1
        doc: '[CONFIRMED_LIVE] raw group id (01..05)'
      - id: segments
        type: segment
        repeat: expr
        repeat-expr: 3
        doc: '[CONFIRMED_LIVE] three 4-byte segment records'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  segment:
    seq:
      - id: brightness
        type: u1
        doc: '[CONFIRMED_LIVE] per-segment brightness'
      - id: colour
        type: govee_common::rgb
        doc: '[CONFIRMED_LIVE] per-segment RGB (shared rgb type)'
  timer_body:
    doc: |
      aa 23 read-back: a 0xff table marker then four 4-byte scheduled-timer slot
      records, mirroring protocol.parse_timer_schedule_table. Live 2026-07-22:
      enabling slot 0 (07:30 Sunday, repeat 0xc0) read back 81 07 1e c0 with the
      enable bit 0x80 set, while the three disabled slots read 01 .. .. .. (enable
      bit clear, on-action bit set).
    seq:
      - id: marker
        contents: [0xff]
        doc: '[CONFIRMED_LIVE] raw 0xff table marker'
      - id: slots
        type: govee_common::timer_slot
        repeat: expr
        repeat-expr: 4
        doc: '[CONFIRMED_LIVE] four 4-byte scheduled-timer slot records (the slot index is positional 0..3)'
