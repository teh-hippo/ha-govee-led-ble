meta:
  id: colormode_readback
  title: Govee H617A "aa 05" colour-mode readback reply
  endian: le
doc: |
  Light -> phone status notification, 20 bytes on the wire:
    aa 05 <mode> <16 mode-specific bytes> <xor>
  byte[19] is the XOR of bytes[0..18]. Kaitai's expression language has no
  fold/reduce, so the checksum is read as an opaque byte and validated by the
  host harness (see roundtrip_aa05.py), never computed in-grammar.
  Re-verified byte-exact against captured frames (fixtures in roundtrip_aa05.py);
  field meanings cross-checked against protocol.parse_color_mode_response.
seq:
  - id: header
    contents: [0xaa]
    doc: status header, raw 0xaa
  - id: domain
    contents: [0x05]
    doc: domain byte, raw 0x05 = colour-mode readback
  - id: mode
    type: u1
    enum: color_mode
    doc: raw colour-mode selector byte
  - id: body
    size: 16
    type:
      switch-on: mode
      cases:
        'color_mode::static': static_body
        'color_mode::scene': scene_id_ref
        'color_mode::diy': diy_body
        'color_mode::video': video_body
        'color_mode::music': music_body
    doc: the 16 bytes at frame offsets 3..18, interpreted per mode
  - id: checksum
    type: u1
    doc: raw XOR of bytes[0..18]; opaque here, validated host-side
enums:
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
  static_body:
    doc: |
      mode 0x15. sub 0x01 carries an RGB triple; 0x02 a white-brightness percent.
      Only sub 0x00 has been seen in a live aa 05 reply; the 0x01 (rgb) and 0x02
      (white-brightness) readback branches are INHERITED from the write-side
      structure, not yet capture-verified (device-verify item).
    seq:
      - id: sub
        type: u1
        enum: static_sub
      - id: rgb
        size: 3
        if: sub == static_sub::rgb
        doc: R,G,B at frame offsets 4..6 when sub == 0x01
  scene_id_ref:
    doc: mode 0x04. Scene effect id, little-endian, at frame offset 3+.
    seq:
      - id: scene_id
        type: u2le
  diy_body:
    doc: mode 0x0a. App-assigned DIY slot at frame offset 3.
    seq:
      - id: slot
        type: u1
  video_body:
    doc: mode 0x00 (H6199). Region/mode/saturation/sound/softness at offsets 3..7.
    seq:
      - id: full_screen
        type: u1
      - id: game_mode
        type: u1
      - id: saturation
        type: u1
      - id: sound_effects
        type: u1
      - id: softness
        type: u1
  music_body:
    doc: |
      mode 0x13. offsets: 3 mode-id, 4 sensitivity, 5 style (Dynamic/Calm, Rhythm only),
      6 manual-colour count / auto flag, 7..9 manual RGB when count >= 1.
    seq:
      - id: mode_id
        type: u1
        doc: raw music mode id (enum pending const.MUSIC_MODES verification)
      - id: sensitivity
        type: u1
      - id: style
        type: u1
      - id: manual_color_count
        type: u1
      - id: rgb
        size: 3
        if: manual_color_count >= 1
