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
    0x23: timer
    0xa5: segments
  color_mode:
    0x15: static
    0x04: scene
    0x0a: diy
    0x00: video
    0x13: music
  static_sub:
    0x01: rgb
    0x02: white_brightness
types:
  power_body:
    seq:
      - id: is_on
        type: u1
        doc: '[CONFIRMED_LIVE] raw power state, 0x00 off / 0x01 on'
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
            'color_mode::diy': cm_diy
            'color_mode::video': cm_video
            'color_mode::music': cm_music
        doc: '[CONFIRMED_LIVE] the 16 bytes at frame offsets 3..18, interpreted per mode'
  cm_static:
    doc: |
      mode 0x15. sub 0x01 carries an RGB triple, 0x02 a white-brightness percent.
      Only sub 0x00 has been seen in a live aa 05 reply; the 0x01 (rgb) and 0x02
      (white-brightness) read-back branches are modelled from the write-side.
    seq:
      - id: sub
        type: u1
        enum: static_sub
        doc: '[CONFIRMED_LIVE] static sub-selector byte (frame offset 3; 0x00 seen live)'
      - id: rgb
        type: govee_common::rgb
        if: sub == static_sub::rgb
        doc: '[INHERITED] R,G,B at frame offsets 4..6 when sub == 0x01 (no capture)'
  cm_scene:
    doc: mode 0x04. Scene effect id, little-endian, at frame offset 3+.
    seq:
      - id: scene_id
        type: u2le
        doc: '[CONFIRMED_LIVE] scene effect id (little-endian) at frame offset 3'
  cm_diy:
    doc: mode 0x0a. App-assigned DIY slot at frame offset 3.
    seq:
      - id: slot
        type: u1
        doc: '[CONFIRMED_LIVE] app-assigned DIY slot at frame offset 3'
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
  cm_music:
    doc: |
      mode 0x13. offsets: 3 mode-id, 4 sensitivity, 5 style (Dynamic 0x00 / Calm 0x01),
      6 manual-colour count / auto flag, 7..9 manual RGB when count >= 1.
    seq:
      - id: mode_id
        type: u1
        enum: govee_common::music_mode
        doc: '[CONFIRMED_LIVE] music mode id (frame offset 3; see govee_common::music_mode)'
      - id: sensitivity
        type: u1
        doc: '[CONFIRMED_LIVE] sensitivity 0..99 (frame offset 4)'
      - id: style
        type: u1
        enum: govee_common::music_style
        doc: '[CONFIRMED_LIVE] Dynamic 0x00 / Calm 0x01 (frame offset 5; see govee_common::music_style)'
      - id: manual_color_count
        type: u1
        doc: '[CONFIRMED_LIVE] manual colour count / auto-colour flag (frame offset 6)'
      - id: rgb
        type: govee_common::rgb
        if: manual_color_count >= 1
        doc: '[CONFIRMED_LIVE] manual RGB at frame offsets 7..9 when count >= 1'
  version_body:
    doc: firmware version, ASCII, NUL-terminated (e.g. "3.02.24")
    seq:
      - id: text
        type: strz
        encoding: ASCII
        doc: '[CONFIRMED_LIVE] firmware version ASCII string, NUL-terminated'
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
  segment:
    seq:
      - id: brightness
        type: u1
        doc: '[CONFIRMED_LIVE] per-segment brightness'
      - id: colour
        type: govee_common::rgb
        doc: '[CONFIRMED_LIVE] per-segment RGB (shared rgb type)'
  timer_body:
    doc: ff-prefixed 4-slot schedule table; slot internals decoded in a later increment
    seq:
      - id: marker
        contents: [0xff]
        doc: '[CONFIRMED_LIVE] raw 0xff table marker'
      - id: slots_raw
        size-eos: true
        doc: '[INHERITED] opaque 4-slot region, not yet field-decoded'
