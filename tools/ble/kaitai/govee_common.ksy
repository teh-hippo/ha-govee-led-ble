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
  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
types:
  rgb:
    doc: |
      One ordered RGB colour triplet, three raw bytes R,G,B on the wire. Proven
      identical across every DIY/scene/workshop/music palette and the aa segment
      read-back, so it is defined once and imported by all of them.
    seq:
      - id: r
        type: u1
        doc: 'red channel 0-255'
      - id: g
        type: u1
        doc: 'green channel 0-255'
      - id: b
        type: u1
        doc: 'blue channel 0-255'
  a3_header:
    doc: |
      The two leading bytes shared by every reassembled 0xA3 multi-frame body:
      01 <linecount>. The A3 payload TYPE byte follows in each payload spec (it is
      payload-specific and disambiguated by the activation frame, so it is not part
      of this shared header). linecount is the 17-byte A3 chunk count and is never
      below 0x02; its per-payload values are documented at each use site.

      IF YOU QUOTE A VENDOR NAME FOR A PAYLOAD TYPE, QUOTE IT AGAINST THIS BYTE.
      Four unrelated integers in the vendor app are all called "version", and they
      disagree: the wire type byte (MULTI_V1_NEW_SCENES = 1, V2 = 2, V3 = 7, V4 = 10),
      the controller class suffix (the class named V3 emits 7 and the one named V5
      emits 10), the cloud catalogue's sceneType, and a separate op-type set used only
      to filter which scenes a device is offered. A name carried across from the wrong
      one of those lands on a different format entirely. The wire byte is the only
      identity that survives, which is why the payload specs name their type in
      numbers first and the vendor's word second.

      HOW TO REASSEMBLE (read this before decoding any A3 capture). Concatenate
      bytes[2:19] of EVERY 0xA3 frame in ARRIVAL order, including the frame whose
      index byte is 0xFF, and stop when you have linecount * 17 bytes. That single
      rule is correct for both framing forms and is the only one that is.

      WHY IT IS EASY TO GET WRONG. The 0xFF index does NOT mean "terminator". The
      sender (protocol.build_a3_multi) emits two different forms and the index byte
      alone cannot tell them apart:
        * terminator form (build_a3_multi terminator=True, and always when the body
          fits one chunk) -- data chunks carry sequential indices 0..n-1 and an EXTRA
          all-zero frame indexed 0xFF is appended. linecount = chunk_count + 1, and
          the appended frame's 17 zeros are exactly the body's trailing padding.
        * plain form -- there is no extra frame; the LAST DATA chunk itself carries
          index 0xFF and holds real payload. linecount = chunk_count.
      Discarding the 0xFF frame as an empty terminator is therefore correct for the
      first form and silently truncates the body by up to 17 bytes in the second.
      That is the common case, not an edge case: of the 46 A3 transactions in the
      capture corpus, 40 are the plain form and only 6 are the terminator form, and
      both forms occur across payload types 0x02, 0x03 and 0x04 (measured
      ).
      The failure is quiet rather than loud: a truncated body still parses as a
      plausible shorter record and presents as a length-field disagreement, which
      invites the wrong conclusion that the grammar is broken. Diagnosed
      while analysing a flat-DIY palette; the shared reader is
      tools/ble/decode_govee.py::reassemble_a3.

      linecount IS A CHECK, NOT A SLICE. For one complete transaction the concatenated
      length always equals linecount * 17 (46 of 46 corpus transactions), so slicing to
      it achieves nothing. Applied to a frame list that is NOT exactly one transaction
      it is destructive: a capture window holding two transactions slices away the
      second entirely, and a duplicated frame silently replaces the real final chunk.
      Segment on index 0x00..0xff first, reassemble one transaction, then use linecount
      to VERIFY the result. This was implemented as a slice on  and reverted
      the same day.
      Both forms are live-confirmed -- Finger Sketch
      uses the terminator form, Vibrant and multi-chunk scene bodies the plain form
      (see diy_type03.ksy for the worked byte counts).
    seq:
      - id: marker
        contents: [0x01]
        doc: 'raw 0x01 generic build_a3_multi body marker'
      - id: linecount
        type: u1
        valid:
          min: 2
        doc: '17-byte A3 chunk count as the sender wrote it, counting the appended empty frame in the terminator form. Equals reassembled_body_len // 17 exactly, in all 46 A3 transactions in the capture corpus, when every frame of ONE transaction is concatenated in arrival order (measured ). Use it to verify a reassembly, never to slice one; see this type''s reassembly rule. Never observed below 0x02: the app never emits a lone frame.'
  sleep_timer:
    doc: |
      Sleep / fade-off timer body, shared byte-for-byte by the 0x11 command write
      and its aa 11 read-back (write 33 11 01 32 10 10 00 <-> read aa 11 00 32 10 10,
      live ). Matches protocol.build_timer_sleep: the light fades from
      start_brightness to off over close_minutes.

      ALL FOUR FIELDS ISOLATED LIVE [drive2-timer ]. The app surface is
      More > Timer > Sleeping, which exposes a "Set countdown" row and an "Initial
      brightness" slider. One sequence separated every field:
        aa 11 00 32 10 10   baseline, matching the UI (50%, 16 mins, toggle off)
        33 11 01 0b 10 10   saved after dragging Initial brightness to 11%
        aa 11 01 0b 10 0c   read 4.5 minutes later, still armed
        33 11 00 0b 10 10   toggled off
        33 11 01 32 10 10   Initial brightness restored to 50%
        33 11 00 32 10 10   toggled off again
      Note the tick on the edit screen SAVES AND ARMS in one action, which is why
      every save carries enabled=01.
    seq:
      - id: enabled
        type: u1
        doc: '0x00 off / 0x01 on; toggled 01<->00 live  (res-timer-sleep-on/off) and again in drive2-timer '
      - id: start_brightness
        type: u1
        doc: 'the app''s "Initial brightness" slider on More > Timer > Sleeping, 0..100, the level the fade starts from. Isolated over two transitions in drive2-timer : 50 -> 0x0b=11 -> 0x32=50, each matching the slider. It tracks THAT CONTROL, not device brightness: device brightness was 5% throughout while this byte read 11. Supersedes the earlier note that the value was "not app-shown, not varied"; it is both shown and now varied.'
      - id: close_minutes
        type: u1
        doc: 'total fade-to-off duration in minutes, the app''s "Set countdown"; 0x10=16 matches "Turn off in 16 minutes" (res-timer-sleep-on). Held at 0x10 across the whole of drive2-timer while current_minutes moved independently, which is what separates the two.'
      - id: current_minutes
        type: u1
        doc: 'countdown minutes REMAINING, a live register rather than a copy of close_minutes. Isolated in drive2-timer : armed at 0x10=16, read 0x0c=12 about 4.5 minutes later with close_minutes still 0x10, and the app independently showed "Turn off in 12 minutes" above a description still reading "within 16 minutes". Resets to close_minutes when the timer is disarmed (33 11 00 0b 10 10).'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  wake_timer:
    doc: |
      Wake / sunrise timer body, shared byte-for-byte by the 0x12 command write and
      its aa 12 read-back (write 33 12 01 64 11 01 00 1d <-> read aa 12 00 64 11 01
      00 1d, live ). Matches protocol.build_timer_wakeup: the light ramps
      to end_brightness by hour:minute over the trailing duration.

      THE ACK DOES NOT MIRROR THE WRITE. A crafted 33 12
      write is acked with a constant 33 12 00 00.., so 0x12 joins 0x04, 0x05, 0x23 and
      0xa3 in that family and only the aa 12 read can verify a change. This is the
      general rule for this protocol, not a per-opcode quirk; see status_reply.ksy.
    seq:
      - id: enabled
        type: u1
        doc: '0x00 off / 0x01 on; toggled 01<->00 live  (res-timer-wake-on/off)'
      - id: end_brightness
        type: u1
        doc: 'target brightness reached at hour:minute, 0..100; 0x64=100 matches the app "reach maximum brightness"'
      - id: hour
        type: u1
        doc: 'wake hour 0..23; 0x11=17 matches the app "17:01" (res-timer-wake-on)'
      - id: minute
        type: u1
        doc: 'wake minute 0..59; 0x01=1 matches the app "17:01"'
      - id: repeat
        type: u1
        doc: |
          Weekday repeat byte. Its OFFSET is pinned by its neighbours,
          which res-timer-wake-on isolated individually (17:01 and a 29-minute ramp), so
          the byte between minute and duration_minutes is this field.

          ITS BIT SEMANTICS ARE NOT SETTLED FOR THIS COMMAND, BUT ITS STORAGE NOW IS.
          The cross-reference that used to stand here, "same encoding as the schedule
          slot: 0x80=fire-once, 0x00=every day", was wrong on both halves and is
          withdrawn. 0x80 is not fire-once anywhere, see timer_slot::repeat.

          THE DEVICE STORES THIS BYTE VERBATIM AND DOES NOT NORMALISE IT.
          Settled by the FIRST 33 12 write in the corpus:
          before this, all 26 aa 12 replies across the 77-capture archive read the
          identical 00 64 11 01 00 1d, every one from a slot whose enabled byte is
          0x00, and the archive held ZERO 33 12 writes, so nothing had ever driven the
          field. A crafted write of 33 12 00 64 11 01 5a 1d (enabled deliberately left
          at 0x00, so nothing was armed) read back as 00 64 11 01 5a 1d. Two things
          follow. The byte is stored, not derived. And bit 0x80 is NOT forced by
          firmware here: 0x5a has it clear and the device kept it clear, which is a
          real difference from the schedule slot, where 0x80 was set in 100% of
          observed values. So the two repeat bytes are NOT interchangeable, and the
          old analogy would have been wrong even had it named the right semantics.
          Restored to 0x00 and verified by read.

          THE WEEKDAY MAPPING IS SETTLED: bit0=Monday THROUGH bit6=Sunday.
          Measured by driving the vendor app's own Repeat
          chips and capturing each write, which is the only instrument that can bind a
          bit to a day: the device accepts arbitrary bit patterns, so a crafted write
          proves storage and nothing about meaning. Three selections, one write each,
          every other field held identical at 64 11 01 .. 1d:

            Mon + Wed + Fri  -> 0x95   bits 0, 2, 4 set, plus bit 7
            no days at all   -> 0x80   bit 7 alone
            all seven days   -> 0x00   nothing set

          So bit 7 is not a day and not a repeat-enable: it marks "this is not the
          every-day case", and it is set even when the selection is EMPTY. All seven
          days collapses to 0x00 rather than to 0x7f, which no bitmap reading would
          predict and which is why the every-day case had to be captured too.

          THE SHIPPED ENCODER AND DECODER ARE EXACTLY RIGHT, which is worth stating
          because two claims that used to stand here were not. protocol.timer_repeat
          returns 0x80 for an empty selection, 0x80|mask for a proper subset and 0x00
          for all seven; protocol.parse_timer_repeat inverts that. Both match all three
          captures byte for byte.

          TWO CORRECTIONS TO THIS DOC, both from the same run. The note that
          parse_timer_repeat "decodes 0x00 as one-time" was wrong: it decodes 0x00 as
          EVERY DAY, and one-time is 0x80. And the flat claim above that "0x80 is not
          fire-once anywhere" does not hold for this command - here 0x80 is precisely
          fire-once, observed directly. It remains true that the firmware does not FORCE
          bit 7, which is the real difference from timer_slot::repeat and the thing the
           crafted write actually established.

          Note the 0x95 agreement with the schedule slot is now a second, independent
          observation of the same encoding rather than an analogy between them.
      - id: duration_minutes
        type: u1
        doc: 'sunrise ramp length in minutes; 0x1d=29 matches the app ramp 16:32->17:01 (res-timer-wake-on)'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  timer_slot:
    doc: |
      One scheduled on/off timer slot [enable_and_type, hour, minute, repeat], shared
      by the 0x23 schedule command write (one slot after the slot index) and the
      aa 23 read-back (four slots after a 0xff marker). Matches
      protocol.build_timer_schedule / parse_timer_schedule.

      THE WHOLE RECORD IS DEVICE-STORED. Three
      single-variable writes to slot 2 were each read back through aa 23 ff and matched
      the write byte for byte, including the repeat byte that had just been changed.
      That matters because the 0x23 ack does NOT mirror the write: every one of the six
      writes in the archive was acked with the same constant 33 23 00 00 .., so the ack
      carries no state and only the aa 23 read is trustworthy. 0x23 is the fourth opcode
      with that property, alongside 0x33 a3, 0x33 04 and 0x33 05.
    seq:
      - id: enable_and_type
        type: u1
        doc: |
          bit 0x80 = slot enabled, bit 0x01 = on-action. Live enabling
          slot 0 read/wrote 0x81 (enabled|on) vs 0x01 disabled ( and
          res-timer-sched-on/off ).

          The two bits were separated on  (capture h617a-timer-) by
          flipping ONLY the slot's action from On to Off, which wrote 0x80: enabled with
          the on-action bit clear. That is the first observation of 0x80 on its own and
          it is what makes the two bits independent rather than a three-value enum.
      - id: hour
        type: u1
        doc: 'scheduled hour 0..23; a 07:30 write echoed hour 0x07'
      - id: minute
        type: u1
        doc: 'scheduled minute 0..59; 0x1e=30 echoed'
      - id: repeat
        type: u1
        doc: |
          Weekday repeat bits, Mon=bit0 .. Sun=bit6. Selecting Mon, Wed
          and Fri in the app wrote 0x95, whose low seven bits are exactly bits 0, 2 and 4,
          which pins the weekday order on this command (capture h617a-timer-,
          re-observed as 33 23 02 81 00 00 95 in h617a-timer-readback-).

          BIT 0x80 IS NOT "FIRE ONCE". That reading was falsified by the same capture: 0x80
          stayed SET alongside three explicit weekdays. It is set in every schedule-slot
          value ever observed (0x80 with the app showing "Do not repeat", 0xc0 with "Sun",
          0x95 with "Mon Wed Fri") and has never been seen clear on this command. Fire-once
          is therefore signalled by the weekday bits being zero, not by a separate flag.
          protocol.timer_repeat was already right, because it emits the bit unconditionally
          as TIMER_REPEAT_ONCE | mask; only the reading was wrong.

          DO NOT RESTATE THE DECODER HERE. This doc used to add that "the converse branch
          in protocol.parse_timer_repeat, which treats a clear 0x80 as one-time, remains
          untested". That was wrong twice over. The function decodes a CLEAR 0x80 as EVERY
          DAY, not as one-time, and sleep_timer::repeat above already says so. The two docs
          contradicted each other for as long as both stood, because a correction landed on
          one and not the other while sleep_timer and timer_slot share the single parser
          protocol.parse_timer_repeat. What is true and specific to THIS command is only
          that a clear 0x80 has never been observed on it.

          THE DEVICE STORES THE BYTE, so this is not merely an app-side convention. After
          the 0x95 write the aa 23 ff read-back returned 01 00 00 95 for slot 2, and
          01 00 00 80 after the restore, byte-identical to each write
          (files/timer-storage.log, ).
  diy_selector:
    doc: |
      DIY effect selector, shared byte-for-byte by the 0x05/0x0a command write
      (33 05 0a <slot> <type_byte>) and its aa 05 0a colour-mode read-back
      (aa 05 0a <slot> <type_byte>). Matches protocol.build_diy_activate and
      protocol.parse_color_mode_response (which reads only the slot).

      SLOT IS AN APP-SIDE ENTRY ID, NOT A DEVICE STORAGE INDEX. [CONFIRMED_LIVE
      ] Activating each of the seven saved "My DIY" entries showed the app
      re-uploads the entry's whole A3 body every time and then names it with a slot;
      it never selects stored content by slot alone. The slots observed were arbitrary
      and one per entry (0x32, 0xbe and 0xf0 for three saved flat DIYs), and a brand-new
      UNSAVED DIY applied from the editor took 0x17, so an id exists before any save.
      Two slots are instead fixed per EDITOR: Finger Sketch always writes 0x20 and the
      Color > Vibrant tab always writes 0x84, each re-confirmed live  across
      several different bodies in one session. Share Space is a THIRD such surface:
      0xfe carried four distinct shared bodies across two sessions (two on
      morning, two more in capture drive3-diy-typebyte), so it is surface-fixed rather
      than a per-entry id. This corrects the earlier claim that 0xf0
      is a "scratch / live-preview" slot: 0xf0 is simply the id of one saved user DIY on
      this account, and the unsaved-apply id was 0x17.
    seq:
      - id: slot
        type: u1
        doc: 'DIY slot: an app-assigned per-entry id, written 33 05 0a and read back aa 05 0a byte-identical. Fixed per SURFACE for Finger Sketch (0x20), Vibrant (0x84) and Share Space (0xfe, confirmed  across four distinct shared bodies); arbitrary per entry for library entries (0x17 unsaved-new, 0x32 / 0x98 / 0xbe / 0xf0 saved flat DIYs). protocol.AUTHORED_DIY_SLOT 0xF0 is one such library id, NOT a reserved scratch value. 0x98 was added 2026-07-27g: it sits in this repo''s own frozen cm_diy fixture (aa 05 0a 98, now spec/status_reply_cm_diy.kst) yet had been omitted from this observation set, which is a reminder to derive the set from the fixtures rather than from prose.'
      - id: type_byte
        type: u1
        doc: |
          DIY family / type byte, observed only as 0x00 or 0x03, echoed back
          verbatim by aa 05 0a. Its meaning is NOT settled.

          IT IS NOT THE A3 BODY TYPE. That reading was
          falsified twice in one sitting by Share Space: applying two different shared
          effects each uploaded a TYPE 0x03 body (01 04 03 ... , parsed exactly by
          diy_type03 with zero excess) and each activated with 33 05 0a fe 00, i.e.
          type_byte 0x00. Re-entering the device page read it back as aa 05 0a fe 00, so
          the device stores the pairing rather than the app merely mis-sending it. Do not
          reinstate the body-type reading without a counter-capture.

          WHY THE OLD READING LOOKED CONFIRMED. It was derived from six activations in
          which the body type and the producing surface covaried perfectly: the only
          0x03 senders were the two live-preview editors, which happen to be the only
          type-0x03 producers we had. Exactly the "correlation is not attribution" trap
          the corpus keeps setting. Share Space breaks the tie because it replays a
          type-0x03 body from a stored entry.

          THE SURVIVING READINGS. Reading (b) below was FALSIFIED on  (capture
          drive3-diy-typebyte) and is kept here so it is not re-derived:
            a) SURFACE CLASS - 0x03 for the live-preview editors that cannot be saved
               (Finger Sketch, Vibrant), 0x00 for anything replayed from a stored entry
               (My DIY library, Share Space). STILL ALIVE.
            b) SLOT OWNERSHIP - 0x03 when the slot is fixed by the editor, 0x00 when the
               slot is an app-assigned per-entry id. DEAD. Two further distinct shared
               effects were applied, each uploading a different TYPE 0x03 body, and each
               activated with 33 05 0a fe 00. That is FOUR distinct bodies on slot 0xfe,
               which is the same bar this spec uses to call 0x20 and 0x84 fixed per
               editor. So 0xfe is fixed by the Share Space SURFACE, not an app-assigned
               id, and (b) then requires 0x03 where 0x00 is observed.
            c) NO INDEPENDENT MEANING - <slot, type_byte> is one 2-byte selector and
               type_byte is simply whatever the app pairs with that slot. NOT EXCLUDED,
               and it explains every byte we hold at least as well as (a) does.

          WHY (a) IS NOT YET A CONFIRMATION. Every 0x03 we hold comes from exactly two
          surfaces, Finger Sketch (0x20) and Vibrant (0x84), so (a) rests on a two-member
          class and cannot be told apart from (c) without a THIRD non-saveable live
          surface. Random Color was tested for exactly that on  and does not
          qualify: it emits no DIY activation at all, only 33 05 15 01 per-segment colour
          writes. The test did not fire, so it moved nothing.

          Full observation set: 0x20/0x03 and 0x84/0x03 (bodies TYPE 0x03);
          0x17, 0x32, 0xbe, 0xf0 all /0x00 (bodies TYPE 0x04); 0xfe/0x00 four times
          (bodies TYPE 0x03, four distinct bodies).

          TO SETTLE IT, find a third non-saveable live editor that emits a DIY activation,
          or any activation carrying a value outside {0x00, 0x03}. A type-0x04 body sent
          with 0x03 would refute (a). Failing an app surface, this is a crafted-frame
          question: send 33 05 0a f0 03 and see whether the device renders or stores
          anything differently from 33 05 0a f0 00. If it does not, (c) is the answer.

          CRAFTED-FRAME RESULT . That test was run. Slot 0xf0
          is a SAVED library DIY whose body is TYPE 0x04 and which the app has only ever
          activated with 0x00. Sending 33 05 0a f0 03 was ACCEPTED, and aa 05 read back
          aa 05 0a f0 03 verbatim; sending 33 05 0a f0 00 read back aa 05 0a f0 00. The
          device therefore stores whatever we pair with the slot and imposes NO constraint
          of its own: it does not coerce, validate or reject a type_byte that reading (a)
          says belongs to a different surface class. That is what (c) predicts, and it
          demotes (a) to at most an APP-SIDE labelling convention rather than device
          semantics.

          WHAT THIS PROBE DID NOT SHOW, stated plainly so it is not over-read: it did not
          compare RENDERING. The aa a5 segment buffer was byte-identical before and after
          both activations, but it was equally unchanged by the activation itself, so it
          is not tracking DIY output and cannot serve as a render observable here. The
          "renders identically" half of the test remains unrun and needs eyes on the strip.
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding within the 16-byte sub / mode window; grammar-enforced all-zero'
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
        doc: 'music mode id (see music_mode)'
      - id: sensitivity
        type: u1
        doc: 'sensitivity 0..99'
      - id: style
        type: u1
        doc: 'raw style byte; Dynamic 0x00 / Calm 0x01 is the Rhythm-only interpretation (other modes repurpose it, see protocol.parse_color_mode_response)'
      - id: manual_color_count
        type: u1
        doc: 'manual colour count / auto-colour flag; 0 = auto-colour, >= 1 = manual RGB supplied'
      - id: rgb
        type: rgb
        if: manual_color_count >= 1
        doc: 'manual RGB when count >= 1; (0,230,210) captured on the write, a manual triple on the read-back'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: 'trailing zero padding within the 16-byte sub / mode window; grammar-enforced all-zero'
  brightness_block:
    doc: |
      The 6-byte brightness sub-block r7..r12 of an effect_layer. Repeated
      brightness_block_count times (r6). Workshop captures only ever carried one, so
      workshop_body.ksy previously modelled these as flat fields and read r6 as an
      unexplained constant 0x01; the frozen scene catalogue supplies the r6 == 2 cases
      (Downpour 2179 rec2/rec3, Birthday rec0) that prove it is a repeat count.

      WHAT THE CATALOGUE'S brightPage SELECTS. [CONFIRMED ] brightPage is the
      index into THIS array, not a record index. The record is chosen by the config
      block's own page. Two independent checks agree with no exceptions: Christmas 2189
      block 1 has page 1 and brightPage 0, and its live write landed in record 1, not
      record 0; and across the whole frozen catalogue the single entry whose brightPage
      is non-zero is Downpour page 2, which is the single record with
      brightness_block_count == 2, and it carries both a brightPage 0 and a brightPage 1
      entry. The other 48 entries are all brightPage 0 on single-block records. This is
      why an earlier audit found brightPage "carries almost no information": nearly every
      record has exactly one brightness block, so the index is almost always 0.

      THE REPEAT CARRIES INDEPENDENT PER-BLOCK DATA []. A repeated block is not
      a duplicate, a padded slot or a restatement of the first: sibling blocks in one
      record hold unrelated values. Downpour 2179 rec2 holds ff0002ff0201 beside
      ff0000fb28c8, and its rec3 holds 0702019b80c8 beside 040303997cc0, differing in
      every one of r7..r12 in that second pair. A decoder must therefore read each block
      in full and must never fold the repeat down to its first element.

      EQUAL SIBLINGS ARE STILL LEGAL, which is the reason this is stated as independence
      rather than as "the blocks differ". Birthday 2190 rec0 carries two blocks that are
      byte-identical (ff1900000000 twice), so difference is permitted, not required, and
      an equality check is not a valid parse gate. All three multi-block records in the
      frozen catalogue are named here because three is the entire population.

      This was settled from the frozen catalogue rather than from the rig, after the
      Workshop editor was shown unable to produce a second block at all. Every type-2
      record was parsed (191 of 191 satisfying the record-length identity), which is what
      makes "three multi-block records" a census rather than a sample.
    seq:
      - id: brightness_scope_start
        -orig-id: r7
        type: u1
        doc: 'r7, high end of the Brightness Scope pair r7:r8 (ff00 default -> c639 for a displayed 22-77%).'
      - id: brightness_scope_end
        -orig-id: r8
        type: u1
        doc: 'r8, low end of the Brightness Scope pair r7:r8.'
      - id: brightness_order
        -orig-id: r9
        type: u1
        enum: brightness_order
        doc: |
          r9, the editor's "Brightness Order" selector, position-indexed
          into its four-option list. Isolated  in the Effects Lab editor: with
          every other control untouched, switching Brightest-Darkest to
          Darkest-Brightest-Darkest and tapping Apply moved this byte 0x00 -> 0x03 and
          NOTHING else in the 29-byte record, its framing or the activation frame. The
          frozen catalogue corroborates the domain exactly: across all 191 type-2 records
          r9 takes the values {0, 1, 2, 3} and no other. Previously carried the pessimistic
          inherited-default tag as "unmapped, 0x00 in every workshop capture" — Workshop
          captures simply never moved it.
          Same four-value idiom as movement.packed's direction bits.

          LABEL COLLISION, DO NOT BE CAUGHT BY IT. The editor
          renames this one selector depending on the Brightness tab: it reads "Brightness
          Order" under Unified and "Distribution Method" under Gradient, with the same
          four options and the same byte behind both. A DIFFERENT control, in the Color
          section, is ALSO labelled "Distribution Method" and drives r13. So the string
          "Distribution Method" on screen maps to r9 or r13 depending on which section it
          sits in, and a screenshot cropped to the row cannot tell you which.
      - id: brightness_speed
        -orig-id: r10
        type: u1
        doc: |
          r10 Brightness Changing Speed (7f/80 ~= 50%, ff = 100%).
          THIS IS THE CATALOGUE'S "bright" BYTE, and finding that out closed the last
          open scene question. A config block's bright[k].brightValue list is written
          here, into record[page].brightness_blocks[k], indexed by the Speed slider
          position. Confirmed live : Forest 2163 walked this byte
          201/216/226/251 across the four slider stops with every other byte of the
          119-byte body identical, and Christmas 2189 moved it in records 1 and 2
          (230->214->221) while record 0, whose config block carries NO bright key,
          held r10 at 0x00 throughout. That negative control is what makes this an
          attribution rather than a fit.
          WHY IT WAS MISSED FOR SO LONG. An offline sweep had already scored this
          location best (36 of 50 controls) and REJECTED it as "semantically wrong",
          because the key is named bright and this field is a speed. The name is
          Govee's and it means brightness-CHANGING-SPEED, not a brightness level.
          There was never a missing brightness field; there was a missing mapping.
      - id: brightest_retention
        -orig-id: r11
        type: u1
        doc: 'r11, Brightest retention of the pair r11:r12 (1414 default -> c830 for displayed 200/48).'
      - id: darkest_retention
        -orig-id: r12
        type: u1
        doc: 'r12, Darkest retention of the pair r11:r12.'
  movement:
    doc: |
      A 3-byte movement sub-block <packed> <interval> <speed>. All three fields are
      isolated live: the packed enable/direction bits by the movement-dir/overall-dir/
      toggle captures, and the interval and speed bytes by the  single-slider
      Workshop captures (Moving Christmas L1), where each Apply moved exactly one byte.
    seq:
      - id: packed
        type: u1
        doc: 'enable bit 0x10, selected-area Enter/Exit bit 0x04, low 2 bits = direction (0 Fwd, 1 Fwd+Back, 2 Back, 3 Back+Fwd).'
      - id: interval
        type: u1
        doc: >
          movement interval: the raw discrete Moving-Interval picker
          level (selected-area range 0-2, overall 0-4+), stored as the literal value.
          Isolated : selected-area r24 01->02 and overall r27 01->02 were
          each the only byte to move.
      - id: speed
        type: u1
        doc: >
          movement speed: a full 0x00..0xff scaled value =
          round(slider_fraction * 255). Isolated : selected-area r25 ef->82
          (51%) and overall r28 b7->56 (34%) were each the only byte to move. The app's
          displayed integer percent is an independent rounding of the same fraction
          (round(fraction * 100)), so the byte is only approximately round(pct * 2.55)
          and differs by 1 at boundaries (34% -> 0x56=86, not round(34*2.55)=87).
          SCENE SIDE: this is the byte the frozen scene catalogue calls moveIn on
          selected_area_movement and moveAll on overall_movement, which is why those
          two names sit 5 and 2 bytes from the end of a record. Confirmed live
           on Christmas 2189, Bloom 2228, Glacier 2175, Fire 2171,
          Winter 2170 and Moonlight 2177: the app writes the scene's per-page option
          list value indexed by the editor's Speed slider position, exactly here.
    instances:
      enabled:
        value: '(packed & 0x10) != 0'
        doc: 'movement enable bit 0x10.'
      enter_exit_effect:
        value: '(packed & 0x04) != 0'
        doc: 'selected-area Enter/Exit bit 0x04 (always 0 for overall movement).'
      direction:
        value: 'packed & 0x03'
        doc: 'low 2 bits: movement direction 0..3.'
  effect_layer:
    doc: |
      One effect layer record body, shared byte-for-byte by the Workshop layer
      container (A3 TYPE 0x02, workshop_body.ksy) and the rgbicv2 scene container
      (scene_body.ksy). Offsets count the record length byte as r0, so the first field
      here is r1.

        r1..r6 | r7..r12 x r6 | r13..r16 | palette 3*M | area move 3 | all move 3 | r_prio

      record_len == 16 + 6*(brightness_block_count - 1) + 3*colour_count + 7, which
      reduces to the long-known workshop form 23 + 3*M when r6 == 1. Verified 191/191
      against every type-2 record in the frozen H617A scene catalogue and byte-exact
      against captured Aurora, Forest, Christmas, Bloom, Glacier and Fire bodies, whose
      palettes decode to the colours those effects actually show.

      PROVENANCE: workshop_body.ksy isolated these fields live one control at a time;
      scene_body.ksy independently re-derived the same layout from the scene corpus and
      supplied the r6 >= 2 case. Sharing the type is therefore a claim of proven
      sameness, per this file's admission rule, and it retires a set of INFERRED
      placeholders that scene_body.ksy carried for years of captures.

      A THIRD, INDEPENDENT CONTROL SURFACE. The Effects Lab
      editor, reached by the pencil badge on a custom-scene tile in the app's My DIY
      list, edits exactly one of these records and names its controls the way this type
      names its fields: Applied Area, Select Type, Number of IC, Color, Distribution
      Method, Direction, Color Changing Speed, Retention Time, and a Brightness section
      whose numbered sub-tabs are the r6 repeat. Reading the editor beside the decoded
      "Hey There" record matched every displayed value byte-exact (Number of IC 15 =
      r4 0x0f; palette red+blue = ff0000 0000ff; Color Changing Speed 50% = r14 0x80;
      Retention Time 20 = r15 0x14; Brightness Changing Speed 50% = r10 0x80; both
      retention times 20 = r11/r12 0x14), and it is what finally isolated r9. This
      matters beyond the field: it is a user-reachable editor, so every field here can
      now be driven directly rather than inferred from stock catalogue content.

      THE CONTROL INVENTORY IS CLOSED. [CONFIRMED_LIVE , capture
      drive3-layer-editor] The editor was scrolled end to end and every control it
      exposes was matched to a field: Applied Area r1, Select Type r2, Number of IC r4,
      Color palette r16 + triplets, Distribution Method r13, Direction r13 bit 0x80,
      Color Changing Speed r14, Retention Time r15, Brightness Unified/Gradient r5 bit
      0x02, the numbered Brightness sub-tabs r6, Brightness Order r9, Brightness Scope
      r7:r8, Brightness Changing Speed r10, Retention Time of the Brightest/Darkest Light
      r11/r12, Moving Effect in the Selected Area and Overall Moving Effect the two
      movement sub-blocks, and Effect Layer Priority the last byte. Name, Icon and DIY
      Group are account metadata and are not in the record. ONE control had no field when
      the inventory was taken, the Brightness Unified/Gradient tab, and driving it is what
      attributed r5 bit 0x02. The layer tab strip above the panel is the record count, not
      a field.

      A whole-record readback was taken in the same session and every displayed value
      matched byte-exact against a 29-byte record: 15 ICs r4 0x0f, one brightness block
      r6 0x01, Scope 100%-100% r7:r8 ffff, Brightest-Darkest r9 0x00, Brightness Changing
      Speed 1% r10 0x02, both retention times 20 r11/r12 0x14, Based-on-IC + Forward r13
      0x01, Color Changing Speed 90% r14 0xe5, Retention Time 102 r15 0x66, two colours
      r16 0x02, both movement toggles off (packed byte 0x00) and Priority off 0x00.
    seq:
      - id: applied_area
        -orig-id: r1
        type: u1
        doc: >
          r1 Applied Area window: high nibble = width in tenths,
          low nibble = start in tenths (0x00 = whole strip). The five Christmas
          workshop layers tile as 20 22 24 26 28 (width 2 at starts 0/2/4/6/8); 0x40
          seen for a [0,4]-tenths window. Scene records carry the same encoding
          (Bloom 0x30/0x23/0x25/0x37, Glacier 0x50/0x55, Stream 0x91).
      - id: select_type
        -orig-id: r2
        type: u1
        enum: select_type
        doc: >
          r2 Select Type: 00 Segment, 01 Select IC Continuously,
          02 Select IC Randomly, 03 Customize Segment. All four seen on the wire with
          the documented r3:r4 parameter pairs. Value 03 DOES ship in H617A content and
          is not editor-only: re-parsing all 72 type-2 params in
          tools/ble/catalogues/effect-library-H617A.json finds it exactly three times,
          at Desert B code 10005 records 1 and 2 and Sand Grains code 10006 record 0.
          That check is reproducible from the frozen catalogue in this repo.
          CORRECTED 2026-07-27g: this doc previously asserted the H617A catalogue "only
          uses 0/1/2", which is false by the parse above, and rested the four-value claim
          on a cross-SKU sweep whose data was never frozen. A later frozen sweep read
          select_type 0, 1, 2 and 3 across independent third-party data; that archive was
          retired on , so the fourth value now rests on the local parse above,
          which finds 0x03 three times and is reproducible from this repo.
      - id: select_param_1
        -orig-id: r3
        type: u1
        doc: >
          r3 Select-Type parameter 1 (meaning depends on r2):
          Segment 00, Continuously 00, Randomly 0f (max ICs), Customize 01.
      - id: select_param_2
        -orig-id: r4
        type: u1
        doc: >
          r4 Select-Type parameter 2 (Number of IC etc.): Segment 07,
          Continuously 0f, Randomly 01 (min ICs), Customize 00.
      - id: layer_flags
        -orig-id: r5
        type: u1
        doc: |
          r5, a bitfield. Two bits are attributed, each by its own
          single-variable differential in the layer editor; the rest read as raw.

          BIT 0x02 = the Brightness section is in GRADIENT mode rather than Unified.
          Isolated  (capture drive3-layer-editor) on the custom scene
          "CopyChristmas": Apply with Brightness=Unified, then tap the Gradient tab and
          Apply again with every other control untouched. The two a3 uploads differ in
          EXACTLY ONE byte, r5 0x10 -> 0x12, and the trailing frame is byte-identical.
          This bit was carried as "still unattributed" until that test. It is not rare
          content: a sweep of a 27-SKU third-party archive read r5 = 0x00, 0x02 and 0x42,
          putting roughly a third of all scenes Govee ships in the brightness-gradient
          layer bucket. That archive was retired on , so the proportion is
          observed history; the attribution itself came from the capture above and stands
          without it.

          BIT 0x10 = this Apply came from an editor session in which something was CHANGED.
          Isolated : the SAME crafted layer (1 layer, Select IC Continuously,
          15 ICs, whole strip, red+blue) applied once before saving and once after,
          differing in exactly one byte. This retracted an
          earlier claim that 0x10 marks a Based-on-Segment distribution: the Distribution
          Method was "Based on Number of IC" in BOTH runs. Consistent with the frozen
          corpus, where 0x10 never appears in shipped content because shipped scenes are
          by definition saved.
          THE EDITOR SURFACE ALONE DOES NOT SET IT []. Applying an
          already-saved, unmodified item from inside the layer editor emitted 0x00
          (CopyChristmas: 1 layer, whole strip, Select IC Continuously, 15 ICs,
          red+green, record_len 29). Applying the saved 5-layer Christmas from the list
          likewise read 0x00 on all five layers.
          SAVING DOES NOT CLEAR IT [CONFIRMED_LIVE , capture
          session-cupboard-20260731-125248]. The doc said until this date that the bit
          tracks unsaved changes. It does not. A 5-layer item was built, SAVED as
          "ChaosTwo", and applied from the editor: 0x12 on all five records. The same
          saved item, untouched, was then applied by tapping its tile in the Workshop
          list, and the two 187-byte bodies differ in EXACTLY five bytes, every one of
          them this r5, 0x12 -> 0x02 at offsets 9/42/75/108/141. Nothing else moved, so
          the bit cannot be reporting anything about the item's content or its saved
          state -- both were identical across the pair.
          What all three experiments jointly support is that the bit marks an Apply issued
          from an editor session that has MODIFIED something, and that a save does not end
          that session. Whether re-entering the editor clears it has not been isolated.
          Per-body, not per-layer: all five records carried the bit identically in both
          bodies, which the earlier one-layer isolation could not show.

          BIT 0x40 is seen exactly once in the 4216-record frozen corpus (as 0x42) and is
          NOT attributed. One sample is a coincidence, not a meaning.
      - id: brightness_block_count
        -orig-id: r6
        type: u1
        doc: >
          r6 = number of 6-byte brightness blocks that follow, and the
          count of numbered sub-tabs in the editor's Brightness section. Every workshop
          capture carried 0x01, which is why it read as a constant there; the frozen
          scene catalogue contains 0x02 records (Downpour 2179 rec2/rec3, Birthday rec0)
          and the record-length identity holds 191/191 only when r6 is treated as this
          repeat count. A 27-SKU third-party archive retired on  also showed
          0x03, all consuming exactly to priority; that third value is now observed
          history rather than reproducible evidence.
      - id: brightness_blocks
        type: brightness_block
        repeat: expr
        repeat-expr: brightness_block_count
        doc: 'brightness_block_count blocks of r7..r12.'
      - id: direction_distribution
        -orig-id: r13
        type: u1
        doc: >
          r13 packed byte: bit 0x80 = Direction Backward, OR-ed with
          the distribution value (00 Unified, 01 Based-on-IC, 02 Based-on-Segment) and
          bit 0x01 = colour-gradient (only meaningful under Based-on-Segment, moving 82
          to 83). Values 01/80/81/82/83 seen on the wire.
      - id: colour_speed
        -orig-id: r14
        type: u1
        doc: >
          r14, Colour Changing Speed of the pair r14:r15 (8014 default;
          7f/82/b2 seen in Workshop). This is the scene byte that resisted explanation
          for several sessions: the scene editor's single Speed slider drives the two
          movement speeds AND, in scenes whose effect cycles colour, this byte.
          Christmas 2189 walks 250/244/237/229 across its four slider positions and
          Moonlight 2177 moves it too, while Bloom, Fire, Winter, Glacier and Summer
          leave it alone. Aurora is the clean illustration: its long-known slow-vs-fast
          two-byte diff is rec0 colour_speed and rec1 selected_area_movement.speed, two
          different fields, which is why it looked inconsistent while the record was
          modelled as an opaque blob. THE DRIVER IS THE CATALOGUE'S "color" LIST, in the
          config block whose page names this record; re-confirmed  with byte
          offsets resolved against record boundaries on Forest 2163 and on all three
          Christmas 2189 records at once. SCALE: the Effects Lab editor showed "Color
          Changing Speed 50%" against this byte reading 0x80, so it is a 0..0xff percent
          scale, not 0..100 (same scale as brightness_speed r10).
      - id: colour_retention
        -orig-id: r15
        type: u1
        doc: 'r15, Colour Retention of the pair r14:r15 (14 default; 6d seen). Raw units, not scaled: the Effects Lab editor showed "Retention Time 20" against this byte reading 0x14.'
      - id: colour_count
        -orig-id: r16
        type: u1
        doc: 'r16 = M, number of RGB triplets in the palette. The record-length identity holds byte-exact for M = 1..6 across the whole H617A scene catalogue and every captured workshop layer. A 27-SKU third-party archive retired on  once extended the tested range to 1..7, 9, 11, 12 and 16 with zero residue; that breadth is observed history, and the tag rests on the local catalogue and captures, which are still here.'
      - id: palette
        -orig-id: r17
        type: rgb
        repeat: expr
        repeat-expr: colour_count
        doc: 'r17..: M ordered RGB triplets. Independently corroborated by decoding captured scene bodies, whose palettes are the colours the effect visibly shows (Aurora 00ff7f/007fff/2aff00, Forest greens plus white).'
      - id: selected_area_movement
        type: movement
        doc: >
          selected-area movement <packed> <interval> <speed>. Its speed
          byte is the value the scene catalogue calls moveIn, 5 bytes from the record end.
      - id: overall_movement
        type: movement
        doc: >
          overall movement <packed> <interval> <speed>. Same enable bit
          and 2-bit direction as selected-area but no Enter/Exit bit (10..13 seen). Its
          speed byte is the value the scene catalogue calls moveAll, 2 bytes from the end.
      - id: priority
        type: u1
        doc: >
          last record byte: the editor's "Effect Layer Priority" toggle,
          00 off / 01..05 levels. Captures show 00/01/02/03. A 27-SKU third-party archive
          retired on  showed the full 00..05 range in shipped content plus 0xff
          on six records; levels 04, 05 and 0xff are therefore observed history rather
          than reproducible evidence. 0xff was never attributed: it is consistent with an
          "unset" sentinel but nothing tested that, and a plausible reading is not a
          confirmed one.
          ISOLATED BYTE-EXACT  (capture session-cupboard-20260731-144121). Two
          51-byte bodies from a one-layer item, differing only in the priority control,
          differ at exactly one offset, 0x00 -> 0x03 at the last byte of the record. So
          both the position and the value are confirmed by a single-variable differential
          rather than inferred from corpus statistics.
          THE TOGGLE ALONE WRITES NOTHING. Switching Effect Layer Priority ON and applying
          produced a body byte-identical to the one before it. The switch reveals a 1..5
          level selector with NOTHING selected, and only choosing a level moves this byte.
          So 00 does not mean "the toggle is off": it also covers "enabled with no level
          chosen", and the two are indistinguishable on the wire. Anything reproducing a
          record must write the level, not a boolean.
      - id: excess
        size-eos: true
        doc: |
          Not a wire field: a structural assertion that the record ENDS
          at priority. Kaitai sizes this substream from rec_len, so any byte landing here
          means the record is longer than the field list above and the layout is wrong.
          Every .kst case asserts it empty, which is also how record_len == 23 + 3*M is
          enforced: the arithmetic cannot be wrong without a byte appearing here.

          EVIDENCE. Empty for every type-2 record in the local frozen catalogue and for
          every captured body, with zero parse failures, and it covers the app's own
          writer, since the editor's Apply upload consumes exactly to priority. A 27-SKU
          third-party archive retired on  once exercised this far wider,
          reaching record_len 26..59 and 71, brightness_block_count 1..3 and colour_count
          up to 16 with no residue anywhere. That breadth is observed history now, so the
          assertion is tested over the H617A range rather than well outside it.
    instances:
      applied_area_width_tenths:
        value: '(applied_area & 0xf0) >> 4'
        doc: 'Applied Area width in tenths (high nibble of r1).'
      applied_area_start_tenths:
        value: 'applied_area & 0x0f'
        doc: 'Applied Area start in tenths (low nibble of r1).'
      direction_is_backward:
        value: '(direction_distribution & 0x80) != 0'
        doc: 'r13 bit 0x80: Direction Backward when set.'
      brightness_is_gradient:
        value: '(layer_flags & 0x02) != 0'
        doc: 'r5 bit 0x02: the Brightness section is in Gradient mode rather than Unified.'
      applied_from_changed_editor:
        value: '(layer_flags & 0x10) != 0'
        doc: 'r5 bit 0x10: this Apply came from an editor session in which something was CHANGED. Named applied_as_draft until  and documented as "applied from the editor without being saved", which the same capture that renamed it falsified: a 5-layer item was SAVED and then applied from the editor, reading 0x12 on all five records, while the identical saved item applied from the list read 0x02. Saving does not clear the bit; leaving the editor is what clears it. See the layer_flags doc above for the full differential.'
enums:
  brightness_order:
    0: brightest_darkest
    1: brightest_darkest_brightest
    2: darkest_brightest
    3: darkest_brightest_darkest
  select_type:
    0: segment
    1: select_ic_continuously
    2: select_ic_randomly
    3: customize_segment
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
