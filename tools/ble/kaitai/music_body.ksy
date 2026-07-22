meta:
  id: music_body
  title: Govee H617A music-mode wire structures (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  Two related H617A music-mode wire structures, verified byte-exact against real
  captures (chiefly 20260716120000-h617a-music-walkthrough.pcap, plus count=7 and
  Day & Night variants from other captures). Captures are ground truth.

  ROOT TYPE `music_body` = the reassembled 0xA3 "MultipleController4Music" 0x41 BODY
  (per-mode movement parameters). The host reassembles the 17-byte A3 chunks
  (frame bytes[2:19] concatenated); the A3 framing/terminator is transport, not
  modelled here. There is NO checksum inside the reassembled body. On-wire layout:
    01 <fragCount> 41 <MODE> <count> <RGB x count> <mode-specific tail> <zero pad>
  The mode-specific tail parameters sit immediately after the palette (RELATIVE to
  palette end, not at a fixed absolute offset): Shiny and Separation appear in
  captures with both count 5 and count 7, and the same tail bytes follow each
  palette (e.g. Shiny tail `05 64 0a` at offsets 20-22 when count 5, and at 26-28
  when count 7). The tail is modelled as ONE per-mode opaque region; individual tail
  parameters are NOT decoded here (their semantics come from protocol.py
  `_MUSIC_PARAM_TEMPLATE`, not from an isolated capture differential), so the whole
  region is tagged as inherited.

  SUB-TYPE `mode_set_frame` = the full 20-byte `33 05 13` music mode-set FRAME. It
  IS a full frame, so byte[19] is the XOR of bytes[0..18], read opaque and validated
  host-side (Kaitai has no fold/reduce; see roundtrip_music.py), exactly like
  colormode_readback.ksy. On-wire layout:
    33 05 13 <MODE> <SENS> <STYLE> <COUNT> <RGB x COUNT> <zero pad to 18> <xor>
  `13` is the music sub-command the current builder ships; an older protocol emits
  0x0c for the same frame (noted, not modelled — every captured frame is 0x13).

  MODE enum matches const.MUSIC_MODES / MUSIC_MODE_SLUGS. Cross-checked against the
  shipped encoders protocol.build_music_params_a3 (0x41 body) and
  protocol.build_music_mode_with_color (mode-set frame).
seq:
  - id: header
    type: govee_common::a3_header
    doc: '[CONFIRMED_LIVE] shared A3 body header 01 <linecount>; here linecount is the fragment count (body length == linecount * 17).'
  - id: command
    contents: [0x41]
    doc: '[CONFIRMED_LIVE] body offset 2, raw 0x41: MultipleController4Music command.'
  - id: mode
    type: u1
    enum: govee_common::music_mode
    doc: '[CONFIRMED_LIVE] body offset 3: raw music-mode selector (see govee_common::music_mode).'
  - id: count
    type: u1
    doc: '[CONFIRMED_LIVE] body offset 4: palette colour count; the RGB region is exactly count triples.'
  - id: palette
    type: govee_common::rgb
    repeat: expr
    repeat-expr: count
    doc: '[CONFIRMED_LIVE] body offsets 5..: count x RGB, byte-exact against captures.'
  - id: tail
    size: tail_len
    doc: |
      [INHERITED] per-mode movement-parameter region, immediately after the palette.
      Modelled as one opaque blob: the raw bytes round-trip byte-exact against
      captures, but no individual tail field is decoded or isolated here.
      Semantics/offsets are inherited from protocol.py `_MUSIC_PARAM_TEMPLATE` (write
      side), e.g. Separation +0=separation point, +1=gradient, +2=volatile companion;
      Shiny +0..+1=style companion (Dynamic 05 64 / Calm 14 46). Capture differentials
      are observed (Separation +1 00->01, Shiny +0..+1, Day & Night +1/+2) but are left
      un-isolated in this opaque model, so the region stays pessimistically opaque.
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: '[CONFIRMED_LIVE] transport zero padding to the A3 17-byte chunk boundary; grammar-enforced all-zero.'
instances:
  tail_len:
    value: >-
      mode == govee_common::music_mode::hopping ? 9 :
      mode == govee_common::music_mode::piano_keys ? 5 :
      mode == govee_common::music_mode::fountain ? 4 :
      mode == govee_common::music_mode::separation ? 3 :
      mode == govee_common::music_mode::shiny ? 3 :
      mode == govee_common::music_mode::day_and_night ? 3 : 2
    doc: |
      Per-mode opaque tail length in bytes (relative, counted from the end of the
      palette). Set to the largest parameter block observed for each mode across ALL
      available captures (not just one), because a single capture can leave trailing
      params zero and under-count the region (Day & Night looked like 2 bytes in the
      walkthrough but a later capture sets a third byte, so it is 3). Default 2 covers
      Bloom (offsets +0..+1). Only the seven param-bearing modes seen in captures are
      covered; the simpler modes (Energetic/Rhythm/Spectrum/Rolling) emit no 0x41 body.
      The region is opaque/INHERITED, so a future capture could extend a length.
types:
  mode_set_frame:
    doc: |
      Full 20-byte `33 05 13` music mode-set frame. byte[19] is the XOR of
      bytes[0..18], opaque here and validated host-side (see roundtrip_music.py).
    seq:
      - id: header
        contents: [0x33]
        doc: '[CONFIRMED_LIVE] frame offset 0, raw 0x33: command header.'
      - id: domain
        contents: [0x05]
        doc: '[CONFIRMED_LIVE] frame offset 1, raw 0x05: colour-mode domain.'
      - id: sub
        contents: [0x13]
        doc: '[CONFIRMED_LIVE] frame offset 2, raw 0x13: music sub-command (older protocol uses 0x0c; not seen live).'
      - id: mode
        type: u1
        enum: govee_common::music_mode
        doc: '[CONFIRMED_LIVE] frame offset 3: raw music-mode selector (see govee_common::music_mode).'
      - id: sensitivity
        type: u1
        doc: '[CONFIRMED_LIVE] frame offset 4: mic sensitivity 0..99 (raw); captures span 0x00/0x2f/0x63.'
      - id: style
        type: u1
        doc: '[CONFIRMED_LIVE] frame offset 5: raw byte; Dynamic 0x00 / Calm 0x01 is the Rhythm-only interpretation (other modes repurpose it, see protocol.parse_color_mode_response).'
      - id: count
        type: u1
        valid:
          max: 4
        doc: '[CONFIRMED_LIVE] frame offset 6: manual colour count AND auto-colour flag (0x00 = auto on, no RGB). Bounded to max 4 (the 12-byte RGB region) so the padding repeat-expr cannot go negative.'
      - id: colors
        type: govee_common::rgb
        repeat: expr
        repeat-expr: count
        doc: '[CONFIRMED_LIVE] frame offsets 7..: count x manual RGB; captures show count 0 or 1.'
      - id: padding
        type: u1
        valid: 0
        repeat: expr
        repeat-expr: 12 - count * 3
        doc: '[CONFIRMED_LIVE] zero padding from after the RGB region up to byte 18; grammar-enforced all-zero.'
      - id: checksum
        type: u1
        doc: '[CONFIRMED_LIVE] frame offset 19: raw XOR of bytes[0..18]; opaque here, validated host-side.'
