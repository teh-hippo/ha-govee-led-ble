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

  Re-verified byte-exact against captured writes (see spec/command_write_*.kst);
  captures are ground truth. Field meanings cross-checked against
  protocol.build_power / build_brightness / build_segment_color / build_color_temp
  / build_segment_brightness / build_scene / build_diy_activate /
  build_music_mode_with_color, which are treated as a fallible oracle: the wire
  bytes win on any disagreement.

  Opcode 0x09 (clock / time-sync) is now modelled below, captured live on device
  connect (the app sends it as the first frame). The timer write family
  0x11 sleep / 0x12 wake / 0x23 scheduled is now modelled below, live-confirmed
   (fresh writes res-timer-sleep/wake/sched-on|off on the single H617A
  connection, each mirrored by its aa read-back); the sleep/wake bodies are shared
  with status_reply via govee_common. The DIY (0x05/0x0a) and music (0x05/0x13)
  sub-command bodies are likewise shared with the matching aa read-backs via
  govee_common::diy_selector / music_selector.

  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
seq:
  - id: header
    contents: [0x33]
    doc: |
      command header, raw 0x33. WHAT IT MEANS: 0x33 is the WRITE
      opcode of a small opcode set over a shared register address space, where the
      byte that follows is the register. It is not a magic/sync byte, not a protocol
      version and not a device-type marker. The three opcodes are 0x33 write,
      0xAA read (status_reply.ksy) and 0xA3 multi-part write (govee_common::a3_header).
      Our own corpus shows the register space is shared: every aa domain at or below
      0x23 has a 33 domain of the same number and the same meaning (01 power,
      04 brightness, 05 multi/colour-mode, 11 sleep, 12 wake, 23 schedule), while the
      read-only registers (06 firmware, 07 hardware, 40 segment count, a5 segments) are
      device identity and capability rather than settings. Corroborated externally
       by independent reverse-engineering of other Govee products, including
      a Govee smart plug with no LEDs at all, which uses the same 0x33 write / 0xAA read
      pair over 01/06/07 - so the opcode cannot be LED-specific.
      CONSULT THE REGISTER NUMBER BEFORE NAMING A BYTE. Attributing aa 04 without
      checking that 33 04 already meant brightness cost us a wrong rename.
  - id: opcode
    type: u1
    enum: command_op
    doc: 'top-level opcode selector byte (frame offset 1)'
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_cmd
        'command_op::brightness': brightness_cmd
        'command_op::clock': clock_cmd
        'command_op::multi': multi_cmd
        'command_op::timer_sleep': govee_common::sleep_timer
        'command_op::timer_wake': govee_common::wake_timer
        'command_op::timer_schedule': timer_schedule_cmd
        'command_op::multi_effect': multi_effect_cmd
    doc: 'bytes 2..18, interpreted per opcode (unmatched opcodes fall back to raw)'
  - id: checksum
    type: u1
    doc: 'raw XOR of bytes[0..18]; opaque, host-validated'
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: multi
    0x09: clock
    0x11: timer_sleep
    0x12: timer_wake
    0x23: timer_schedule
    0xa3: multi_effect
  multi_sub:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
  multi_effect_cmd:
    doc: |
      op 0xa3, the write side of the register that status_reply reads as aa a3. A
      single flag byte then zero padding. Only the value 0x00 has ever been captured,
      and the device acks it by echoing 33 a3 00.

      WHERE IT APPEARS. It is a PROLOGUE to a batch of
      per-segment static colour writes, seen from two independent app surfaces:
      More > Random Color () and More > Color Slider's palette apply
      (). In both, 33 a3 00 is the first frame sent, immediately followed by
      one 33 05 15 01 <rgb> <mask> write per segment. Nothing else in the app has been
      seen to touch the register, and neither surface writes it again afterwards.

      WHAT THE FLAG MEANS IS STILL OPEN , BUT THE REGISTER IS NOW PROVEN
      WRITEABLE. A crafted frame settled the half of this
      that observation could not. Writing 33 a3 01 and re-reading gave aa a3 01;
      writing 33 a3 00 again gave aa a3 00. So the device ACCEPTS and STORES 0x01, and
      aa a3 is a genuine state read-back rather than an echo. The width is at least one
      value beyond 0x00 and the read-back tracks what we write. Watch out for the ack:
      33 a3 01 is acked with 33 a3 00, so the ack does not mirror the written value and
      only the aa a3 read can be trusted.

      0x01 RENDERS NOTHING, AND THAT NEGATIVE IS NOW OBSERVED RATHER THAN ASSUMED.
      Tested with a human watching the strip, against a
      deliberately hard-boundary paint: segments 1..5 red, 6..10 green, 11..15 blue,
      applied as three masked 33 05 15 01 frames, so any blend would show as softened
      junctions. Four observations. (1) Baseline at flag 0x00: three equal blocks,
      hard junctions. (2) Writing 33 a3 01 with NO repaint: no visible change, so it
      is not a live render mode. (3) Re-sending the byte-identical batch under 0x01:
      no visible change, junctions still hard. (4) A FLICKER test, because the eye
      detects change far better than absolute difference: fifteen cycles alternating
      33 a3 00 + repaint against 33 a3 01 + repaint on a two-second cadence, 121
      frames, with the repaint common to both halves so it could not masquerade as the
      effect. No visible change at any point.

      So the two external projects documenting 33 a3 01 as "Gradient On" are NOT
      transferable to the H617A, and a third documenting 33 14 01 for the same
      function is no better supported. One corroborating argument needs no observation
      at all: the app emits 33 a3 00 as the PROLOGUE to its own fifteen-frame Color
      Slider gradient batch, so the app renders a gradient with this flag at ZERO.

      WHAT IT ACTUALLY DOES REMAINS OPEN, AND THE LIKELIEST READING IS THAT WE ARE NOT
      USING IT RIGHT. The register persists, reads back on aa a3, and is mirrored in
      the aa 05 static reply (see status_reply.ksy cm_static::sub), so it is plainly
      live state and not a no-op. What has never been observed is the app writing
      anything other than 0x00, which means every test so far has driven the register
      into a state the vendor firmware may never be asked to render.
      WALKTHROUGH HOOK, and we EXPECT IT TO FAIL: during the end-to-end app walkthrough,
      watch every capture for a 33 a3 frame whose flag is not 0x00. If one ever appears,
      record exactly what the app was doing at that moment, because that context is the
      missing half. A walkthrough that completes without ever seeing a non-zero flag is
      a RECORDED OUTCOME, not a gap: it would say the vendor app never uses the value
      the device happily stores.

      IT IS NOT A TRANSACTION BRACKET. IT SURVIVES LOSS OF MAINS POWER.
      This was the cheap test this note used to ask for, and
      it went against the prologue reading. 33 a3 01 was written and confirmed by read;
      mains power was then cut for about fifteen seconds and restored; aa a3 read 0x01
      again with nothing else touched. So the flag is PERSISTENT STORED STATE, a mode bit
      the device keeps across a cold boot.

      TWO CONTROLS MAKE THAT ATTRIBUTABLE, and without them the result would have been
      worthless in either direction. (1) A LINK-DROP CONTROL RAN FIRST: after the write
      the BLE connection was closed and thirty-five seconds passed with no connection to
      the device at all, and aa a3 still read 0x01. So a 0x00 after the power cut could
      not have been blamed on the reconnect, and the 0x01 we did get is not an artefact
      of one. (2) THE CUT IS PROVEN RATHER THAN ASSUMED: the aa a5 millisecond counter
      went from 79,547,895 ms to 86,314 ms across it (see status_reply.ksy segment_body).
      A register that "survived" a cut which never actually happened is the obvious way
      to get this wrong.

      The prologue position fits a "clear the running multi-frame effect before painting
      segments individually" reading, which would make 0x00 the only value the app ever
      needs on this path and would explain why every captured aa a3 reads all-zero. That
      survives ONLY as a description of where the app puts the frame. Persistence across
      a cold boot rules it out as an account of what the register is.

      NO CHEAP TEST IS LEFT. Write acceptance, read-back, the aa 05 mirror, persistence
      and render-inertness under five separate observations are all now established, and
      not one of them says what the value means. The remaining lead is the walkthrough
      hook above: catch the app writing a non-zero flag and record what it was doing. The
      flag was restored to 0x00 after every probe.
    seq:
      - id: flag
        type: u1
        doc: 'captured from the app only as 0x00, from two surfaces, always as the prologue to a per-segment paint batch. A crafted 33 a3 01 was accepted and stored on 2026-07-27c (aa a3 read back 0x01, then 0x00 again after restore), so the value set is wider than 0x00. It also SURVIVES A MAINS POWER CYCLE, read back as 0x01 after a cut proven by the aa a5 counter resetting, with a link-drop control run first (), so it is persistent stored state and not a per-connection or per-transaction bracket. It stays INFERRED on the same standard applied to clock_cmd flag1: knowing a byte is stored is not knowing what it controls, and what 0x01 changes is still not established.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  power_cmd:
    doc: op 0x01. On/off flag then zero padding.
    seq:
      - id: is_on
        type: u1
        doc: 'raw power state, 0x00 off / 0x01 on'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  brightness_cmd:
    doc: op 0x04. Whole-strip brightness as a raw 0..100 percentage (NOT 0..255 scaled).
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
        doc: 'whole-strip brightness 0..100 raw; 51% -> 0x33 captured (resume-bright-main)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  clock_cmd:
    doc: |
      op 0x09. Wall-clock time-sync the app pushes as the first frame on every
      connect. Live differential (device connect at 16:43:16 then 16:51:29,
      ): the minute byte moved 0x2b->0x33 and the second byte 0x10->0x1d
      exactly tracking the phone clock, the hour held 0x10=16. Body is
      hour/minute/second then a weekday byte, flag1, and the local UTC offset as
      signed hours plus an unsigned minute remainder; the rest is zero-padded.
      Weekday isolated across days : a Friday connect read
      33 09 16 16 03 05 01 0a (22:22:03, weekday 0x05), one calendar day after the
      0x04 Thursday captures, so the byte is the day of week with Mon=1 (Thu=4,
      Fri=5); flag1=0x01 and the UTC offset was +10:00 across all three captures.

      NO protocol.py BUILDER EXISTS, AND ANYONE ADDING ONE MUST READ THE OFFSET FIRST.
      The 0x0a 0x00 in every capture above is UTC+10:00, i.e. this rig's timezone, not a
      protocol constant. A builder that copies it from a capture would ship UTC+10 to
      every user on earth. Derive both components from the local offset instead.

      IT CAN NOW BE READ BACK. aa a5 group 0x31 returns a
      live clock (hour, minute and second isolated by a timed double-read), so this
      register is no longer write-only and no longer needs a connect capture to
      observe. See status_reply::segments_body. The read-back does NOT use this body
      layout field for field: there a zero byte separates minute from second, the
      weekday trails at index 10 and flag1 at index 11.

      THE WHOLE BODY IS NOW A CLOSED LOOP. Crafted writes
      verified by aa a5 31 reads settled several things at once, with the app closed and
      the Home Assistant entry released.
      (1) Hour, minute and second are echoed back exactly as written.
      (2) The weekday is STORED VERBATIM, not derived: driving it to 0x06 on a Tuesday
          read back 0x06. Six of six writes matched.
      (3) NEITHER REGISTER GATES THE FRAME. Writing flag1 = 0x00 and, separately,
          utc_offset_hours = 0x00 was accepted each time and the clock took, so neither
          byte is validated. They were varied ONE AT A TIME, because a frame changing
          both could not attribute a rejection to either.
      (4) BOTH REGISTERS ARE STORED AND MIRRORED, in different groups of the aa a5 window.
          flag1 is at group 0x31 index 11 and utc_offset_hours at group 0x32 index 1. Both were
          proven with arbitrary non-binary sentinels so a coincidence between one-bit
          states was excluded: flag1 read back 0x05, 0x5a and 0x3c as written, and
          utc_offset_hours completed a full round trip 0x0a -> 0x5a -> 0x0a with its sentinel
          appearing nowhere else across a 27-group sweep. So calling these "two
          constant flag bytes" understated them; they are registers, not padding.

      THE OFFSET MEANING IS NOW LIVE-CONFIRMED. The phone
      was changed from Australia/Sydney (+10:00) to Australia/Adelaide (+09:30), the
      vendor app connected and performed its normal sync, and aa a5 group 0x32 changed
      to indices 1..2 = 09 1e. The phone was restored to Sydney without reopening the
      app and the device still returned 09 1e, proving these are stored hour and minute
      components written by the Adelaide sync rather than values consulted at read time.
    seq:
      - id: hour
        type: u1
        valid:
          max: 23
        doc: 'hour 0..23; 0x10=16 matched the wall clock in both connect captures'
      - id: minute
        type: u1
        valid:
          max: 59
        doc: 'minute 0..59; 0x2b=43 -> 0x33=51 tracked the wall clock across two connects'
      - id: second
        type: u1
        valid:
          max: 59
        doc: 'second 0..59; 0x10=16 -> 0x1d=29 changed with elapsed time'
      - id: weekday
        type: u1
        doc: 'day of week, Mon=1; isolated across days: 0x04 on Thu , 0x05 on Fri  (byte tracked the calendar day)'
      - id: flag1
        type: u1
        doc: '0x01 in every app capture, but NOT a constant and NOT ignored. It is a stored 8-bit register mirrored at status_reply aa a5 31 body index 11: crafted writes of 0x05 and 0x5a read back exactly, 6 of 6 driven writes matched, and the clock write was accepted every time so the byte does not gate the frame. WHAT IT CONTROLS is still unestablished, which is why this stays INFERRED. NO IMMEDIATE VISIBLE EFFECT []: driven to 0x5a with eyes on a solid blue strip at 100% and about 20 s of settling, storage confirmed by read-back in the same window, and nothing changed. That rules out a fast visible effect and nothing more: it may act on a timescale, in a mode, or against a condition absent from the trip. Recasting it as a constant is NOT available either, since it is a demonstrably stored register. Its read-back makes it cheap to test further: drive it and watch for any device behaviour that follows.'
      - id: utc_offset_hours
        type: s1
        doc: 'signed whole-hour component of the phone local UTC offset. Australia/Sydney app syncs stored 0x0a (+10); changing the phone to Australia/Adelaide and reconnecting the app stored 0x09 while the following field stored 0x1e, exactly +09:30, read back through status_reply aa a5 group 0x32 on . Restoring the phone to Sydney without reopening the app left 09 1e stored, proving this is device state written during sync. Earlier crafted writes established the byte is mirrored at group 0x32 index 1 and is not frame-gating.'
      - id: utc_offset_minutes
        type: u1
        valid:
          max: 59
        doc: 'unsigned minute remainder of the phone local UTC offset. It was 0x00 in every Sydney (+10:00) connect capture, then stored and read back as 0x1e after an Adelaide (+09:30) app sync on . The half-hour observation separates this field from the zero padding that follows.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window after the confirmed UTC offset minute field; grammar-enforced all-zero'
  multi_cmd:
    doc: |
      op 0x05. Second-level dispatcher: the first body byte selects the sub-command,
      the remaining 16 bytes are interpreted per sub. Mirrors the aa colour-mode
      read-back selectors (scene 0x04 / diy 0x0a / static 0x15 / music 0x13).
    seq:
      - id: sub
        type: u1
        enum: multi_sub
        doc: 'sub-command selector (frame offset 2)'
      - id: sub_body
        size: 16
        type:
          switch-on: sub
          cases:
            'multi_sub::scene': scene_activate
            'multi_sub::diy': govee_common::diy_selector
            'multi_sub::music': govee_common::music_selector
            'multi_sub::static': static_cmd
        doc: 'the 16 bytes at frame offsets 3..18, interpreted per sub-command'
  scene_activate:
    doc: |
      sub 0x04. Two-byte little-endian scene/effect code, then a scene-type byte.

      NAMING WARNING. Two different bytes in two different frames are both called a
      "type" in this spec set, and they are independent:
        * THIS field (activation frame offset 5) -- 0x00 / 0x02 on the H617A.
        * The A3 BODY type byte at reassembled-body offset 2, modelled as
          scene_body.ksy `scene_type` (values 0/1/2, the frozen catalogue's
          scene_type) and as workshop_body.ksy `a3_type` (constant 0x02). Those two
          are the SAME byte under two names.
      Proven independent live : an Effects Lab edit of Forest uploaded an A3
      body whose type byte was 0x02 yet activated with THIS byte 0x00, while a Workshop
      effect uploaded an A3 body whose type byte was also 0x02 and activated with THIS
      byte 0x02. Do not infer one from the other.

      On the H617A every library scene, edited scene, and Effects Lab effect
      activates with type 0x00; Workshop (33 05 04 91 01 02, code 0x0191, see
      workshop_body.ksy) is the only H617A activation that uses type 0x02. The H6199
      uses this byte differently, so the encoding is model-specific and nothing here
      applies to it. Scenes
      that carry a custom rgbicv2 palette upload their BODY (palette/records) as a
      separate multi-frame a3 (scene_body.ksy) immediately before this frame, while
      simpler built-in scenes activate by bare code with no body: live
      Effects Lab Lightning-A 0x0875 uploaded a 3-frame scene_body then activated,
      whereas Sunset 0x0001 sent only the bare code. This frame itself just
      activates a code; protocol.build_scene emits the bare code with type 0x00.
    seq:
      - id: code
        type: u2le
        doc: |
          scene/effect code, little-endian (frame offset 3). Live
          0x0873 (Forest) and 0x0875 (Effects Lab Lightning-A) upload a scene_body
          first; 0x0001 (Sunset) activates code-only with no body.

          TWO CODES ARE RESERVED AND ARE NOT CATALOGUE IDS. Both name a container
          rather than an effect, so the same code is reused for completely different
          content and the device cannot report WHICH one is running:
            * 0x0191 (401) Workshop, always with scene_type 0x02. Body is
              workshop_body.ksy. Confirmed live .
            * 0x0192 (402) user-authored Effects Lab scene, with scene_type 0x00.
              Body is an ordinary A3 TYPE 0x02 scene_body.ksy body. Confirmed live
              : all four custom scenes on the test account activated with
              this one code while carrying completely different bodies, and the
              connect-time read-back reports it as aa 05 04 92 01. Re-confirmed
               from a THIRD producer: AI > Image Effect uploads a
              cloud-generated 4-record body and activates it with the same 402.
          Neither appears in the frozen catalogue
          (tools/ble/catalogues/effect-library-H617A.json), so a decoder that maps a
          code to a catalogue name MUST expect a miss here and degrade gracefully
          rather than reporting a wrong or empty effect.

          THE FROZEN CATALOGUE IS ALSO INCOMPLETE, WHICH IS A SEPARATE PROBLEM.
          More > Light Up Your Life is a curated gallery
          (tabs Daily / Festival / Emotion; rows Morning, Afternoon, Leisure, Twilight,
          Night) that applies its tiles as ORDINARY scenes: upload an A3 TYPE 0x02
          scene_body, then 33 05 04 <code> 00. Two adjacent tiles gave codes 0x284a
          (10314) and 0x284b (10315), and NEITHER is in the frozen snapshot, which
          holds 80 scenes / 83 effects. They are not reserved container codes like 401
          and 402: they sit in the same 10000+ band as catalogue entries we do hold
          (10005 Desert B, 10006 Sand Grains, 10565 White Light, 16160 Aurora B), so
          they are real per-effect ids from a larger cloud catalogue our snapshot never
          captured. A code miss therefore does NOT imply a container code, and
          refreshing the snapshot will not necessarily close the gap.

          The tile's music-note badge is COSMETIC as far as the device is concerned:
          a badged tile and a plain tile produced identically shaped traffic, differing
          only in body length and code, with no 33 05 13 music frame. It marks app-side
          audio, not a device mode.
      - id: scene_type
        type: u1
        doc: 'scene-type byte (frame offset 5). 0x00 for every H617A scene/effect activation (library scene, edited scene, Effects Lab, and user-authored Effects Lab scene code 0x0192); 0x02 only for Workshop (code 0x0191). Live : Forest 0x0873 and Effects Lab Lightning-A 0x0875 both 0x00, an edited-then-reapplied Forest stays 0x00. The 36/37 3f 02 activations once noted here are H6199 (out of scope), not H617A'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding within the 16-byte sub window; grammar-enforced all-zero'
  segment_mask:
    doc: |
      15-bit segment-selection bitmap, little-endian: segment k (1-based) sets bit
      (k-1), 0x7fff selects all 15 segments. The identical field carries the target
      of both the 33 05 15 01 colour write (offsets 12..13) and the 33 05 15 02
      brightness write (offsets 5..6). Proven on the wire: 0x007f = segments 1..7,
      0x7f80 = segments 8..15 (union 0x7fff = all), 0x4000 = segment 15 alone, and
      0x0001 = segment 1 alone, captured  by selecting exactly ONE segment
      in Color > Subsection and moving its relative brightness. That single-bit case
      is the cleanest proof of the bit-to-segment correspondence and of the
      little-endian order, since the two mask bytes read 01 00 on the wire.

      AN INDEPENDENT CONFIRMATION FROM DEVICE SEMANTICS. [CONFIRMED_LIVE ,
      capture drive3-random-color] More > Fun Lighting > Random Color paints a generated
      scheme in THREE writes using patterned masks rather than fifteen single-segment
      ones, and those three masks settle the byte order without appealing to our encoder
      at all. On the wire they are 11 11, aa 2a and 44 44. Read little-endian they are
      0x1111, 0x2aaa and 0x4444, which select {1,5,9,13}, {2,4,6,8,10,12,14} and
      {3,7,11,15}: a partition of segments 1..15 with no overlap and no gap. Read in raw
      byte order, aa 2a becomes 0xaa2a, which selects a segment 16 that does not exist on
      a 15-segment strip and leaves segment 8 unpainted. Only one reading describes a
      device that works. This matters because the earlier proofs all traced back to
      protocol.py or to single-bit masks that cannot distinguish byte order; this one is
      the device's own behaviour, and it is also the first multi-bit mask captured.
    seq:
      - id: bits
        type: u2le
        doc: 'segment bitmap, little-endian (segment k -> bit k-1); 0x7fff = all 15 segments'
  static_cmd:
    doc: |
      sub 0x15. Static-colour family, third selector byte: 0x01 sets colour (a direct
      RGB paint OR a colour-temperature word, distinguished by which slots are
      populated), 0x02 sets brightness for a masked set of segments, and 0x03 sets the
      relative brightness of EVERY segment in one frame. 0x01 and 0x02 carry the shared
      segment_mask (colour at frame offsets 12..13, brightness at offsets 5..6; 0x7fff
      selects all segments); 0x03 needs no mask because it addresses the whole strip
      positionally. 0x03 was added  after a per-segment snapshot restore
      emitted it and the switch below silently swallowed it as raw bytes.
    seq:
      - id: static_sub
        type: u1
        doc: 'static sub-selector (frame offset 3); 0x01 colour, 0x02 masked segment brightness, 0x03 whole-strip per-segment brightness'
      - id: static_body
        size: 15
        type:
          switch-on: static_sub
          cases:
            0x01: static_color
            0x02: static_brightness
            0x03: static_brightness_all
        doc: 'the 15 bytes at frame offsets 4..18, interpreted per static sub'
  static_color:
    doc: |
      static sub 0x01. One unified layout covers both a direct RGB paint and a
      colour-temperature set: a direct-RGB set populates rgb_direct (offsets 4..6)
      and leaves kelvin/rgb_preview zero; a colour-temperature set zeroes rgb_direct
      and populates kelvin (offsets 7..8, big-endian) plus an RGB companion (offsets
      9..11). A colour-temperature set forces the mask to all-segments (0x7fff); a
      direct paint may select a segment subset (mask != 0x7fff). This shared layout
      is proven on the wire: direct red (all), 3600K temperature (all), and a
      segments-8..15 subset paint (seg-multicolor).

      A GRADIENT IS FIFTEEN OF THESE, NOT AN A3 UPLOAD.
      More > Color Slider generates a palette from one picked colour and applies it as
      a batch of single-segment writes: one 33 a3 00 prologue (command_write
      multi_effect_cmd), then exactly fifteen 33 05 15 01 frames, each carrying a
      single-bit mask, together covering bits 0..14 once each. This is a different
      mechanism from Vibrant, which paints the same visual result by uploading one A3
      TYPE 0x03 body (diy_type03.ksy). Two consequences for anything consuming a
      capture:
        * The batch ARRIVES OUT OF SEGMENT ORDER. The complementary apply was sent
          14, 9, 6, 3, 12, 15, 11, 13, 10, 8, 4, 7, 2, 1, 5. Reconstruct the strip from
          each frame's mask, never from arrival order, and do not treat the last frame
          as the whole-strip state.
        * The ramp is LINEAR IN RGB, NOT gamma-corrected. Applying the complementary
          pair to (116,255,255) produced R 116,125,135,145,...,255 with G and B falling
          255..116 in the same even steps. That is not merely "consistent with" linear,
          it discriminates: componentwise linear interpolation over 14 intervals
          reproduces every one of the 15 samples to within 1 (rounding), whereas the
          gamma-2.2 interpolation protocol._interpolate performs for Vibrant
          (_VIBRANT_GAMMA, measured ) deviates by up to 16 on the same
          endpoints. So the two surfaces genuinely disagree numerically and neither is
          "the" Govee gradient algorithm. Match the surface being reproduced.
    seq:
      - id: rgb_direct
        type: govee_common::rgb
        doc: 'direct RGB paint at offsets 4..6 (zero for a colour-temperature set); (255,0,0) captured (resume-color-red)'
      - id: kelvin
        type: u2be
        doc: 'colour temperature in kelvin, big-endian, offsets 7..8 (zero for a direct RGB paint); 0x0e10=3600 captured (resume-colortemp), and re-confirmed  with 0x0ce4=3300 and 0x2134=8500 from the Color > Whole temperature slider. Big-endian is settled by those values: read little-endian they would be 58380 and 13345, which are not colour temperatures.'
      - id: rgb_preview
        type: govee_common::rgb
        doc: 'RGB companion for a colour-temperature set, offsets 9..11 (zero for a direct RGB paint); (255,203,141) captured for 3600K, (255,195,124) for 3300K and (223,229,255) for 8500K. The bytes clearly encode a temperature-related colour, but whether firmware renders them, reports them or ignores them beside Kelvin is not isolated.'
      - id: mask
        type: segment_mask
        doc: 'segment selection at offsets 12..13 (see segment_mask); 0x7fff for colour/temperature, 0x7f80 = segments 8..15 captured for a subset paint (seg-multicolor)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding within the 15-byte static window; grammar-enforced all-zero'
  static_brightness:
    doc: |
      static sub 0x02. Per-segment (or whole-strip) brightness as a raw 0..100
      percentage, then the shared segment_mask. Emitted live by the H617A app's
      segment editor (a per-segment brightness slider). build_segment_brightness /
      build_white_brightness produce the same frame.

      IT IS A SECOND BRIGHTNESS AXIS THAT MULTIPLIES WITH OPCODE 0x04, NOT A
      DUPLICATE OF IT. "Distinct from the whole-strip
      opcode 0x04" was asserted here from the app surface alone. Settled directly,
      with a human watching the strip, in three observations.

      (1) Writing this frame at the all-segments mask does NOT move opcode 0x04's
      register: aa 04 read 100 before and after, so they are separate state.
      (2) A flicker test against a master-brightness control of the same shape showed
      this frame dimming the strip just as visibly, so it is a live render control
      and not an accepted-then-ignored write.
      (3) The decisive one. Master was PINNED at 20 (verified on 20 consecutive aa 04
      reads during the run) while this frame alternated 100 and 20. The strip pulsed
      clearly darker than the already-dim baseline, so the two compound rather than
      one clamping or overriding the other. 20 of 20 against 20 of 100 is the whole
      finding: an override would have sat still.

      There is NO read-back. aa 05 15 answers with the 33 a3 register and an all-zero
      payload whatever this is set to (status_reply::cm_static), so a write here can
      be verified only by looking at the strip.
    seq:
      - id: percent
        type: u1
        valid:
          max: 100
        doc: 'brightness 0..100 raw at offset 4; 0x11=17% over segments 1..7 and 0x01=1% over segment 15 captured (seg-brightness), 0x1f=31% captured  from the Color > Subsection relative-brightness slider, and 0x14=20% against 0x64=100% driven directly  for the compounding proof in this type''s doc'
      - id: mask
        type: segment_mask
        doc: 'segment selection at offsets 5..6 (see segment_mask); 0x007f = segments 1..7 and 0x4000 = segment 15 captured (seg-brightness)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding within the 15-byte static window; grammar-enforced all-zero'
  static_brightness_all:
    doc: |
      static sub 0x03. The whole strip's per-segment relative brightness in ONE frame:
      the 15-byte static window carries one raw 0..100 percentage per segment, index i
      holding segment i+1. No mask, because every segment is addressed.

      ISOLATED , capture drive3-static03, and it was found because a snapshot
      restore emitted it. Applying a per-segment snapshot replays 33 04 <brightness>, a
      33 a3 00 prologue, 15 single-segment 33 05 15 01 colour writes covering segments
      1..15 once each, and then THIS frame as the last write. Nothing in the specs,
      protocol.py or docs modelled sub 0x03, and an unmatched Kaitai switch falls through
      to raw bytes, so the grammar had been silently accepting it.

      TWO INDEPENDENT CONFIRMATIONS, in one capture. First, the payload read
      1f 64 64 ... while the app's Color > Subsection screen displayed segment 1 at 31%
      and segments 2..15 at 100%, a fifteen-value match in order which also pins the
      direction: the distinctive value sits at index 0, not index 14, so the array is not
      reversed. Second, a differential: selecting ONLY segment 3 and moving its relative
      brightness to 67% changed exactly one payload byte, index 2, to 0x43, and the live
      slider write that accompanied it was 33 05 15 02 43 04 00, whose mask 0x0004 is
      segment 3. The array index and the mask bit therefore agree on the same segment
      through two different frame families.

      SCOPE. This strip has 15 segments and the static window is 15 bytes, so one byte
      per segment fits exactly. Whether a strip with more segments pages this frame,
      widens it or uses something else is UNTESTED and must not be assumed.
    seq:
      - id: segment_percent
        type: u1
        valid:
          max: 100
        repeat: eos
        doc: 'one raw 0..100 relative-brightness percentage per segment, index i = segment i+1; 1f 64 43 64.. captured with segment 1 at 31%, segment 3 at 67% and the rest at 100%'
  timer_schedule_cmd:
    doc: |
      op 0x23. One scheduled on/off timer slot: the slot index then the shared
      timer_slot record (govee_common). protocol.build_timer_schedule. Live
      : enabling slot 0 (07:30, repeat 0xc0) wrote 33 23 00 81 07 1e c0,
      disabling wrote 33 23 00 01 07 1e c0 (enable bit 0x80 cleared). The aa 23
      read-back of the four-slot table is modelled in status_reply.timer_body.

      A second, single-variable series on slot 2 (capture h617a-timer-)
      walked enable -> action -> repeat one byte at a time, which is what separated
      the two bits of enable_and_type and falsified the old "0x80 = fire once" reading
      of repeat:

        33 23 02 81 00 00 80   enable the slot, app shows On / Do not repeat
        33 23 02 80 00 00 80   action On -> Off, enable bit still set
        33 23 02 80 00 00 95   repeat -> Mon+Wed+Fri, 0x80 STAYS SET
        33 23 02 81 00 00 80   restore action
        33 23 02 01 00 00 80   restore disabled
        33 23 02 81 00 00 95   enabled|on with weekdays (readback capture)

      THE ACK IS NOT AN ECHO. All six writes were acked with the constant
      33 23 00 00 .., so a write is only verified by the aa 23 read-back.
    seq:
      - id: index
        type: u1
        doc: 'slot index 0..3; 0x00 written live (res-timer-sched-on/off) and 0x02 written live , each landing in the matching positional slot of the aa 23 four-slot table'
      - id: slot
        type: govee_common::timer_slot
        doc: 'the scheduled slot record (enable_and_type / hour / minute / repeat)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
