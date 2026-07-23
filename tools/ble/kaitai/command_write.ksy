meta:
  id: command_write
  title: Govee H617A "33" command-write envelope (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  Phone -> light control write, 20 bytes: 33 <opcode> <17-byte body> <xor>.
  byte[19] is the XOR of bytes[0..18]; opaque here and validated host-side
  (Kaitai has no fold/reduce). This is the write-side counterpart of the aa
  status_reply envelope: one envelope for the whole 33 control family, with the
  per-opcode bodies below. Opcode 0x05 is a second-level dispatcher whose first
  body byte selects a sub-command (scene / diy / music / static), and the
  static sub-command carries a third selector (colour vs brightness).

  Re-verified byte-exact against captured writes (see roundtrip_command.py);
  captures are ground truth. Field meanings cross-checked against
  protocol.build_power / build_brightness / build_segment_color / build_color_temp
  / build_segment_brightness / build_scene / build_diy_activate /
  build_music_mode_with_color, which are treated as a fallible oracle: the wire
  bytes win on any disagreement.

  Observed H617A opcodes NOT modelled here (fall back to raw; whole-corpus scan
  2026-07-23): 0x09 clock / time-sync; 0x11 sleep timer (build_timer_sleep);
  0x12 wake timer (build_timer_wakeup); 0x23 scheduled timer (build_timer_schedule,
  whose aa 23 read-back IS modelled in status_reply). The 0x11/0x12/0x23 frames
  match those builders byte-exact in 20260716131200-h617a-timer.pcap but that
  capture's connection address is unresolved; queued for on-phone confirmation
  before modelling (validation_backlog timer-write-family, cmd-clock-0x09).

  Every field carries one evidence tag in its doc: [CONFIRMED_LIVE] proven by a
  round-tripped capture; [INFERRED] reasoned but the value is not isolated in a
  capture; [INHERITED] modelled from the write-side/docs with no confirming
  capture (the pessimistic default).
seq:
  - id: header
    contents: [0x33]
    doc: '[CONFIRMED_LIVE] command header, raw 0x33'
  - id: opcode
    type: u1
    enum: command_op
    doc: '[CONFIRMED_LIVE] top-level opcode selector byte (frame offset 1)'
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_cmd
        'command_op::brightness': brightness_cmd
        'command_op::multi': multi_cmd
    doc: '[CONFIRMED_LIVE] bytes 2..18, interpreted per opcode (unmatched opcodes fall back to raw)'
  - id: checksum
    type: u1
    doc: '[CONFIRMED_LIVE] raw XOR of bytes[0..18]; opaque, host-validated'
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
  multi_sub:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
  power_cmd:
    doc: op 0x01. On/off flag then zero padding.
    seq:
      - id: is_on
        type: u1
        doc: '[CONFIRMED_LIVE] raw power state, 0x00 off / 0x01 on'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  brightness_cmd:
    doc: op 0x04. Whole-strip brightness as a raw 0..100 percentage (NOT 0..255 scaled).
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
        doc: '[CONFIRMED_LIVE] whole-strip brightness 0..100 raw; 51% -> 0x33 captured (resume-bright-main)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  multi_cmd:
    doc: |
      op 0x05. Second-level dispatcher: the first body byte selects the sub-command,
      the remaining 16 bytes are interpreted per sub. Mirrors the aa colour-mode
      read-back selectors (scene 0x04 / diy 0x0a / static 0x15 / music 0x13).
    seq:
      - id: sub
        type: u1
        enum: multi_sub
        doc: '[CONFIRMED_LIVE] sub-command selector (frame offset 2)'
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'multi_sub::scene': scene_activate
            'multi_sub::diy': diy_activate
            'multi_sub::music': music_cmd
            'multi_sub::static': static_cmd
        doc: '[CONFIRMED_LIVE] the 16 bytes at frame offsets 3..18, interpreted per sub-command'
  scene_activate:
    doc: |
      sub 0x04. Two-byte little-endian scene/effect code, then a scene-type byte.
      On the H617A every library scene, edited scene, and Effects Lab effect
      activates with type 0x00; Workshop (33 05 04 91 01 02, code 0x0191, see
      workshop_body.ksy) is the only H617A activation that uses type 0x02. The
      scene BODY (palette/records) rides a separate a3 multi-frame upload
      (scene_body.ksy); this frame only activates a code. protocol.build_scene
      emits the bare code with type 0x00.
    seq:
      - id: code
        type: u2le
        doc: '[CONFIRMED_LIVE] scene/effect code, little-endian (frame offset 3); live 0x0873 (Forest), 0x0875 (Effects Lab Lightning-A)'
      - id: scene_type
        type: u1
        doc: '[CONFIRMED_LIVE] scene-type byte (frame offset 5). 0x00 for every H617A scene/effect activation (library scene, edited scene, Effects Lab); 0x02 only for Workshop (code 0x0191). Live 2026-07-23: Forest 0x0873 and Effects Lab Lightning-A 0x0875 both 0x00, an edited-then-reapplied Forest stays 0x00. The 36/37 3f 02 activations once noted here are H6199 (out of scope), not H617A'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte sub window; grammar-enforced all-zero'
  diy_activate:
    doc: |
      sub 0x0a. Activates a DIY effect by its app slot, then a family/type byte. The
      scratch / live-preview slot 0xf0 (the app re-uploads the body each apply, so it
      carries its own TYPE) and Share Space replay (slot 0xfe) send type_byte 0x00; a
      SAVED Finger Sketch / Vibrant (the shared TYPE 0x03 body family) re-activates
      from its numbered slot with type_byte 0x03. All other saved DIYs (TYPE 0x04
      Flat / Combo) send type_byte 0x00. type_byte is NOT keyed on "Finger Sketch":
      Finger Sketch previewed from the scratch slot 0xf0 sends 0x00 (finger-sketch-*),
      and Vibrant (slot 0x84) also sends 0x03.
    seq:
      - id: slot
        type: u1
        doc: '[CONFIRMED_LIVE] DIY slot (frame offset 3). 0xf0 = scratch / live-preview slot, reused across many effects (resume-diy-hello, finger-sketch-*, combo, ...); 0xfe = Share Space replay (h617a-share-space-apply); saved DIYs use app-assigned values (0x20 saved Sketch, 0x84 saved Vibrant, plus 0x1b/0x32/0x6e/0xbe/0xef and others captured)'
      - id: type_byte
        type: u1
        doc: '[INFERRED] DIY family / type byte (frame offset 4). Across the full 205-pcap corpus 0x03 appears ONLY on slots 0x20 (saved Sketch) and 0x84 (saved Vibrant); every other slot (scratch 0xf0, Share Space 0xfe, and all saved TYPE 0x04 slots) sends 0x00. Mechanism (saved TYPE-0x03 family vs slot value) still wants one controlled on-phone capture: create + SAVE a Sketch, re-activate from its tile, confirm 0x03 with its assigned slot; save a Combo, confirm 0x00'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte sub window; grammar-enforced all-zero'
  music_cmd:
    doc: |
      sub 0x13. Music-mode selector plus its inline parameters. Byte layout mirrors
      the aa colour-mode music read-back: mode id, sensitivity, style, manual-colour
      count, then one manual RGB triple when the count is >= 1 (auto-colour when 0).
      Per-mode movement/animation parameters ride a separate 0x41 a3 body (music_body.ksy).
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
        doc: '[CONFIRMED_LIVE] raw byte 5; Dynamic 0x00 / Calm 0x01 is the Rhythm-only interpretation (other modes repurpose it, see protocol.parse_color_mode_response)'
      - id: manual_color_count
        type: u1
        doc: '[CONFIRMED_LIVE] manual colour count / auto-colour flag (frame offset 6); 0 = auto-colour, >=1 = manual RGB supplied. count 1 captured (resume-music-rhythm)'
      - id: rgb
        type: govee_common::rgb
        if: manual_color_count >= 1
        doc: '[CONFIRMED_LIVE] manual RGB at frame offsets 7..9 when count >= 1; (0,230,210) captured'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte sub window; grammar-enforced all-zero'
  segment_mask:
    doc: |
      15-bit segment-selection bitmap, little-endian: segment k (1-based) sets bit
      (k-1), 0x7fff selects all 15 segments. The identical field carries the target
      of both the 33 05 15 01 colour write (offsets 12..13) and the 33 05 15 02
      brightness write (offsets 5..6). Proven on the wire: 0x007f = segments 1..7,
      0x7f80 = segments 8..15 (union 0x7fff = all), 0x4000 = segment 15 alone.
    seq:
      - id: bits
        type: u2le
        doc: '[CONFIRMED_LIVE] segment bitmap, little-endian (segment k -> bit k-1); 0x7fff = all 15 segments'
  static_cmd:
    doc: |
      sub 0x15. Static-colour family, third selector byte: 0x01 sets colour (a direct
      RGB paint OR a colour-temperature word, distinguished by which slots are
      populated), 0x02 sets brightness. Both carry the shared segment_mask: colour at
      frame offsets 12..13, brightness at offsets 5..6; 0x7fff selects all segments.
    seq:
      - id: static_sub
        type: u1
        doc: '[CONFIRMED_LIVE] static sub-selector (frame offset 3); 0x01 colour, 0x02 brightness'
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            0x01: static_color
            0x02: static_brightness
        doc: '[CONFIRMED_LIVE] the 15 bytes at frame offsets 4..18, interpreted per static sub'
  static_color:
    doc: |
      static sub 0x01. One unified layout covers both a direct RGB paint and a
      colour-temperature set: a direct-RGB set populates rgb_direct (offsets 4..6)
      and leaves kelvin/rgb_preview zero; a colour-temperature set zeroes rgb_direct
      and populates kelvin (offsets 7..8, big-endian) plus a preview RGB (offsets
      9..11). A colour-temperature set forces the mask to all-segments (0x7fff); a
      direct paint may select a segment subset (mask != 0x7fff). This shared layout
      is proven on the wire: direct red (all), 3600K temperature (all), and a
      segments-8..15 subset paint (seg-multicolor).
    seq:
      - id: rgb_direct
        type: govee_common::rgb
        doc: '[CONFIRMED_LIVE] direct RGB paint at offsets 4..6 (zero for a colour-temperature set); (255,0,0) captured (resume-color-red)'
      - id: kelvin
        type: u2be
        doc: '[CONFIRMED_LIVE] colour temperature in kelvin, big-endian, offsets 7..8 (zero for a direct RGB paint); 0x0e10=3600 captured (resume-colortemp)'
      - id: rgb_preview
        type: govee_common::rgb
        doc: '[CONFIRMED_LIVE] preview RGB for a colour-temperature set, offsets 9..11 (zero for a direct RGB paint); (255,203,141) captured for 3600K'
      - id: mask
        type: segment_mask
        doc: '[CONFIRMED_LIVE] segment selection at offsets 12..13 (see segment_mask); 0x7fff for colour/temperature, 0x7f80 = segments 8..15 captured for a subset paint (seg-multicolor)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 15-byte static window; grammar-enforced all-zero'
  static_brightness:
    doc: |
      static sub 0x02. Per-segment (or whole-strip) brightness as a raw 0..100
      percentage, then the shared segment_mask. Emitted live by the H617A app's
      segment editor (a per-segment brightness slider), distinct from the whole-strip
      opcode 0x04: captured at 17% over segments 1..7 and 1% over segment 15
      (seg-brightness). build_segment_brightness / build_white_brightness produce the
      same frame.
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
        doc: '[CONFIRMED_LIVE] brightness 0..100 raw at offset 4; 0x11=17% and 0x01=1% captured (seg-brightness)'
      - id: mask
        type: segment_mask
        doc: '[CONFIRMED_LIVE] segment selection at offsets 5..6 (see segment_mask); 0x007f = segments 1..7 and 0x4000 = segment 15 captured (seg-brightness)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 15-byte static window; grammar-enforced all-zero'
