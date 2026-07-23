meta:
  id: govee_common
  title: Govee H617A shared BLE wire datatypes (imported by the per-payload specs)
  endian: le
doc: |
  Provably-common wire structures shared across the H617A protocol specs, defined
  once here and imported so they cannot drift between payloads. A structure earns a
  place here only if it is multi-field (or a drift-prone enum dataset) AND used by
  two or more specs; single-use structures stay local to their spec, and single
  self-validating fields (such as trailing zero padding, valid: 0) stay inline.
  Captures are ground truth: every importing spec round-trips real bytes that
  exercise these types, so sharing is a claim of proven sameness, not convenience.
  Evidence tags follow the same vocabulary as the payload specs:
  [CONFIRMED_LIVE] / [INFERRED] / [INHERITED].
types:
  rgb:
    doc: |
      One ordered RGB colour triplet, three raw bytes R,G,B on the wire. Proven
      identical across every DIY/scene/workshop/music palette and the aa segment
      read-back, so it is defined once and imported by all of them.
    seq:
      - id: r
        type: u1
        doc: '[CONFIRMED_LIVE] red channel 0-255'
      - id: g
        type: u1
        doc: '[CONFIRMED_LIVE] green channel 0-255'
      - id: b
        type: u1
        doc: '[CONFIRMED_LIVE] blue channel 0-255'
  a3_header:
    doc: |
      The two leading bytes shared by every reassembled 0xA3 multi-frame body:
      01 <linecount>. The A3 payload TYPE byte follows in each payload spec (it is
      payload-specific and disambiguated by the activation frame, so it is not part
      of this shared header). linecount is the 17-byte A3 data-chunk count and is
      never below 0x02; its per-payload values are documented at each use site.
    seq:
      - id: marker
        contents: [0x01]
        doc: '[CONFIRMED_LIVE] raw 0x01 generic build_a3_multi body marker'
      - id: linecount
        type: u1
        valid:
          min: 2
        doc: '[CONFIRMED_LIVE] 17-byte A3 frame count as the sender wrote it; equals reassembled_body_len // 17 in every observed capture. Some senders count an appended empty 0xFF terminator frame, others do not (see per-payload docs). Never observed below 0x02.'
  sleep_timer:
    doc: |
      Sleep / fade-off timer body, shared byte-for-byte by the 0x11 command write
      and its aa 11 read-back (write 33 11 01 32 10 10 00 <-> read aa 11 00 32 10 10,
      live 2026-07-23). Matches protocol.build_timer_sleep: the light fades from
      start_brightness to off over close_minutes.
    seq:
      - id: enabled
        type: u1
        doc: '[CONFIRMED_LIVE] 0x00 off / 0x01 on; toggled 01<->00 live 2026-07-23 (res-timer-sleep-on/off)'
      - id: start_brightness
        type: u1
        doc: '[INFERRED] brightness the fade starts from, 0..100; 0x32=50 observed once (not app-shown, not varied), name from build_timer_sleep'
      - id: close_minutes
        type: u1
        doc: '[CONFIRMED_LIVE] total fade-to-off duration in minutes; 0x10=16 matches the app "Turn off in 16 minutes" (res-timer-sleep-on)'
      - id: current_minutes
        type: u1
        doc: '[INFERRED] countdown minutes remaining; 0x10=16 at start (equals close_minutes), name from build_timer_sleep, not independently isolated'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  wake_timer:
    doc: |
      Wake / sunrise timer body, shared byte-for-byte by the 0x12 command write and
      its aa 12 read-back (write 33 12 01 64 11 01 00 1d <-> read aa 12 00 64 11 01
      00 1d, live 2026-07-23). Matches protocol.build_timer_wakeup: the light ramps
      to end_brightness by hour:minute over the trailing duration.
    seq:
      - id: enabled
        type: u1
        doc: '[CONFIRMED_LIVE] 0x00 off / 0x01 on; toggled 01<->00 live 2026-07-23 (res-timer-wake-on/off)'
      - id: end_brightness
        type: u1
        doc: '[CONFIRMED_LIVE] target brightness reached at hour:minute, 0..100; 0x64=100 matches the app "reach maximum brightness"'
      - id: hour
        type: u1
        doc: '[CONFIRMED_LIVE] wake hour 0..23; 0x11=17 matches the app "17:01" (res-timer-wake-on)'
      - id: minute
        type: u1
        doc: '[CONFIRMED_LIVE] wake minute 0..59; 0x01=1 matches the app "17:01"'
      - id: repeat
        type: u1
        doc: '[CONFIRMED_LIVE] weekday repeat bits Mon=bit0..Sun=bit6, same encoding as the schedule slot: 0x80=fire-once, 0x00=every day. Live 0x00 matches the app "Every day" (res-timer-wake-on) and protocol.timer_repeat'
      - id: duration_minutes
        type: u1
        doc: '[CONFIRMED_LIVE] sunrise ramp length in minutes; 0x1d=29 matches the app ramp 16:32->17:01 (res-timer-wake-on)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  timer_slot:
    doc: |
      One scheduled on/off timer slot [enable_and_type, hour, minute, repeat], shared
      by the 0x23 schedule command write (one slot after the slot index) and the
      aa 23 read-back (four slots after a 0xff marker). Matches
      protocol.build_timer_schedule / parse_timer_schedule.
    seq:
      - id: enable_and_type
        type: u1
        doc: '[CONFIRMED_LIVE] bit 0x80 = slot enabled, bit 0x01 = on-action; live enabling slot 0 read/wrote 0x81 (enabled|on) vs 0x01 disabled (2026-07-22 and res-timer-sched-on/off 2026-07-23)'
      - id: hour
        type: u1
        doc: '[CONFIRMED_LIVE] scheduled hour 0..23; a 07:30 write echoed hour 0x07'
      - id: minute
        type: u1
        doc: '[CONFIRMED_LIVE] scheduled minute 0..59; 0x1e=30 echoed'
      - id: repeat
        type: u1
        doc: '[CONFIRMED_LIVE] weekday repeat bits Mon=bit0..Sun=bit6, 0x80=fire-once; 0xc0 = once|Sunday echoed, matches parse_timer_repeat (weekday order live-confirmed 2026-07-09)'
  diy_selector:
    doc: |
      DIY effect selector, shared byte-for-byte by the 0x05/0x0a command write
      (33 05 0a <slot> <type_byte>) and its aa 05 0a colour-mode read-back
      (aa 05 0a <slot> <type_byte>). Matches protocol.build_diy_activate and
      protocol.parse_color_mode_response (which reads only the slot). type_byte is a
      DIY family byte: across the corpus 0x03 appears only on a saved Sketch (slot
      0x20) or saved Vibrant (slot 0x84); scratch 0xf0, Share Space replay 0xfe and
      every saved TYPE-0x04 (Flat / Combo) slot send 0x00.
    seq:
      - id: slot
        type: u1
        doc: '[CONFIRMED_LIVE] DIY slot: 0xf0 scratch / live-preview, 0xfe Share Space replay, saved DIYs app-assigned (0x20 saved Sketch, 0x84 saved Vibrant, ...); written 33 05 0a and read back aa 05 0a byte-identical'
      - id: type_byte
        type: u1
        doc: '[CONFIRMED_LIVE] DIY family / type byte, observed byte-exact both directions (write 33 05 0a 84 03, read aa 05 0a 84 03): 0x03 only for saved Sketch (0x20) / Vibrant (0x84), 0x00 otherwise. The saved-TYPE-0x03-vs-slot mechanism is reasoned, not isolated by a controlled save-and-reactivate capture'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte sub / mode window; grammar-enforced all-zero'
  music_selector:
    doc: |
      Music-mode selector plus its inline parameters, shared byte-for-byte by the
      0x05/0x13 command write (33 05 13 <mode> <sens> <style> <count> [rgb]) and its
      aa 05 13 colour-mode read-back. mode id, sensitivity, style, manual-colour count,
      then one manual RGB triple when the count is >= 1 (auto-colour when 0). Matches
      protocol.build_music_mode_with_color / parse_color_mode_response. Per-mode
      movement parameters ride a separate 0x41 a3 body (music_body.ksy); the full
      20-byte 33 05 13 mode-set FRAME with its own checksum is music_body.mode_set_frame.
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
        doc: '[CONFIRMED_LIVE] music mode id (see music_mode)'
      - id: sensitivity
        type: u1
        doc: '[CONFIRMED_LIVE] sensitivity 0..99'
      - id: style
        type: u1
        doc: '[CONFIRMED_LIVE] raw style byte; Dynamic 0x00 / Calm 0x01 is the Rhythm-only interpretation (other modes repurpose it, see protocol.parse_color_mode_response)'
      - id: manual_color_count
        type: u1
        doc: '[CONFIRMED_LIVE] manual colour count / auto-colour flag; 0 = auto-colour, >= 1 = manual RGB supplied'
      - id: rgb
        type: rgb
        if: manual_color_count >= 1
        doc: '[CONFIRMED_LIVE] manual RGB when count >= 1; (0,230,210) captured on the write, a manual triple on the read-back'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding within the 16-byte sub / mode window; grammar-enforced all-zero'
enums:
  music_mode:
    0x05: energetic
    0x03: rhythm
    0x04: spectrum
    0x06: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
