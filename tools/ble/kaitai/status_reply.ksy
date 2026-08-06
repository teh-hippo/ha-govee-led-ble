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
  Re-verified byte-exact against captured replies (see spec/status_reply_*.kst);
  captures are ground truth. Field meanings cross-checked against
  protocol.split_status_frame / parse_color_mode_response / parse_fw_version /
  parse_hw_version.
  THE ANSWERING SET IS LARGER THAN THE APP REVEALS. [CONFIRMED_LIVE 2026-07-29] Every
  domain modelled here was found because the vendor app asks for it, which makes the list
  app-shaped rather than device-shaped. A direct sweep of 31 unqueried domains found a
  TWELFTH that answers: aa 0f returns a body whose first byte is 0x0f, i.e. query
  aa 0f 00 00... comes back aa 0f 0f 00 00..., reproduced 3 of 3 in a confirmation run
  interleaved with controls. It is deliberately NOT modelled and NOT named: on this strip
  15 is simultaneously the segment count, the 0x40 unit count, the colour-region extent
  and the plausible IC count, so a second register reading 15 separates nothing, and
  naming it after any of them would repeat the unearned label this project already had to
  retract from 0x40. Note only, as an observation: 0x40 answers 00 0f and 0x0f answers
  0f 00, the same two bytes in the opposite order.

  A REPLY IS NOT AN ANSWER IF IT IS BYTE-IDENTICAL TO THE QUERY. In the same sweep
  aa 0e and aa ff produced notifications whose bodies are all-zero, hence indistinguishable
  from an echo of the query frame. They are recorded as undecided, not as new domains. Only
  aa 0f carries a non-zero body. This is the same trap that has twice nearly become a
  finding, on 0xa3 and on 0x01.

  NEITHER DOES aa 26, AND THAT DISPOSES OF AN EXTERNAL CLAIM. [CONFIRMED_LIVE 2026-07-29]
  A compiled external reference lists 0x26 as a "status flags" domain, with no data format
  given, derived from cloud MQTT op.command payloads rather than from BLE and on a model it
  does not state. Queried three times here with no notification on any of them, in a burst
  where aa 40 and aa 0f both answered, so the silence is a result and not a dead link.
  Transport numbering does not carry across. 0x25 and 0x27 were silent in the same burst,
  recorded as observation only since no prediction covered them.

  aa 41 DOES NOT ANSWER ON THIS DEVICE. [CONFIRMED_LIVE 2026-07-29] Queried in the sweep
  and again afterwards, with no notification either time, exactly like 0x14. This matters
  because protocol.parse_poweroff_memory is shipped claiming an aa 41 reply of
  [enabled, mode]; it is marked EXPERIMENTAL with no live capture, and there is now a
  negative measurement against it on the H617A. An external fuzz of one other model reports
  0x41 as power-off memory there, which is a lead for that model and not evidence here.

  SWEEP HAZARD, RECORDED AFTER THE FACT. The 2026-07-29 sweep included aa ff and aa 0e
  before it was known that on an external model those are respectively a device that
  softlocked and needed a power cycle, and a restart register. Our reads were passive and
  the H617A answered benignly, but that was luck rather than diligence. Do not sweep 0xff
  or 0xee again, and treat any unqueried domain as write-unsafe until shown otherwise.

  ONE OBSERVED H617A DOMAIN IS STILL NOT MODELLED here (falls back to raw), attributed
  on the full connect query->reply burst live 2026-07-24 (fw 3.02.24, hw 3.01.01):
  0x14, which the H617A answers NOT ONCE however often it is queried, so its purpose
  is unknown and there is no reply to model. Scope that to the H617A deliberately.
  The corpus also holds two H6199 captures, and one of them does carry a single aa 14
  reply whose body is MAC-shaped. That is a different model on a different firmware
  line, so the reading must never be used to infer H617A behaviour, and no spec here
  models it. No count is quoted for the H617A queries because check-kaitai.sh already
  treats hand-copied figures as drift-prone.
  Domain 0xa3 WAS in that list until 2026-07-28 and is now modelled below as
  multi_effect_body, because it is RESOLVED as a genuine state read-back rather than
  an echo. [CONFIRMED_LIVE 2026-07-27c] Its reply was byte-identical to the query in
  all 28 matched pairs across 20 captures, spanning static, scene, off and music
  states, which could never settle the question by observation alone: the checksum is
  the XOR of bytes 0..18, so an all-zero body and a bare echo of the query serialise
  to the same 20 bytes. A crafted frame separated them. Writing 33 a3 01 and re-reading
  gave aa a3 01, and writing 33 a3 00 again gave aa a3 00, so the reply MIRRORS stored
  state. Every corpus reply was all-zero because the app only ever writes 0x00, not
  because the register is inert. Note the immediate ack to 33 a3 01 is 33 a3 00, i.e.
  the ack does NOT mirror the written value, so only the aa a3 read is trustworthy.
  THIS IS A GENERAL RULE, NOT AN a3 QUIRK. [CONFIRMED_LIVE 2026-07-27e] Writing
  33 04 07 likewise acked 33 04 00 while the aa 04 read correctly returned 07. Never
  read a written value back off the ack; issue the matching aa query. The family of
  opcodes confirmed to ack with a constant rather than a mirror is now 0x01, 0x04, 0x05,
  0x12, 0x23 and 0xa3; 0x12 was added 2026-07-28 by the first crafted 33 12 write, and
  0x01 the same day by a headless power A/B (33 01 01 and 33 01 00 both acked 33 01 00).
  Treat non-mirroring as the DEFAULT for any opcode not yet checked.
  Brightness (0x04) and the 0x40 count were raw here until 2026-07-26 and are now
  modelled below. The sleep-timer (0x11) and wake-timer (0x12) read-backs are also
  modelled below, sharing govee_common.sleep_timer / wake_timer with the 0x11 /
  0x12 command writes (write<->read-back byte-identical, live 2026-07-23). The
  colour-mode DIY (0x0a) and music (0x13) read-backs likewise share
  govee_common::diy_selector / music_selector with the matching 33 05 writes.
  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
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
        'aa_domain::brightness': brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': version_body
        'aa_domain::hw_version': hw_version_body
        'aa_domain::segments': segments_body
        'aa_domain::unit_count': unit_count_body
        'aa_domain::timer': timer_body
        'aa_domain::multi_effect': multi_effect_body
        'aa_domain::sleep_timer': govee_common::sleep_timer
        'aa_domain::wake_timer': govee_common::wake_timer
    doc: '[CONFIRMED_LIVE] bytes 2..18, interpreted per domain (unmatched domains fall back to raw)'
  - id: checksum
    type: u1
    doc: '[CONFIRMED_LIVE] raw XOR of bytes[0..18]; opaque, host-validated'
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0x11: sleep_timer
    0x12: wake_timer
    0x23: timer
    0x40: unit_count
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x15: static
    0x04: scene
    0x0a: diy
    0x13: music
types:
  multi_effect_body:
    doc: |
      domain 0xa3 read-back: a single flag byte then zero padding, the same shape as
      the 0xa3 write. Structured exactly like power_body / power_cmd, the other
      register whose write and read-back share a one-byte body: each side keeps its
      own local type rather than sharing one through govee_common, whose admission
      rule wants a structure to be multi-field before it is shared.

      WHAT THE FLAG MEANS lives once on command_write::multi_effect_cmd and is not
      restated here. What matters on this side is that the reply is a genuine state
      read-back and not an echo of the query, which is what earns this domain a
      modelled body at all. See this spec's top-level doc for the crafted-frame
      evidence, and cm_static::sub for the same register surfacing inside the aa 05
      colour-mode reply.

      EVERY CAPTURED REPLY IS ALL-ZERO. [CONFIRMED_LIVE] 35 replies across 26 captures
      carry one distinct payload, flag 0x00, because the app only ever writes 0x00.
      The grammar therefore round-trips the corpus reply, while the crafted 0x01
      read-back proves the field is not a constant.
    seq:
      - id: flag
        type: u1
        doc: '[INFERRED] read-back of the 0xa3 register. 0x00 in all 35 corpus replies; read back as 0x01 immediately after a crafted 33 a3 01 write and 0x00 again after restore (2026-07-27c), so it tracks stored state. What the value MEANS is open and is documented once on command_write::multi_effect_cmd::flag.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  power_body:
    doc: |
      domain 0x01 power read-back: is_on then zero padding.
      NOTE a frame of the shape aa 01 0c 00 01 00 27 11 24 <b9> 17 <b11> 01 00 00 00
      was once recorded here as a "second, longer aa 01 form" emitted by the H617A.
      That attribution was WRONG and is retracted (offline corpus re-derivation,
      2026-07-25). All 31 instances across the whole capture corpus arrive on ATT
      handle 0x099d, whereas every genuine Govee frame uses handle 0x0010 (notify)
      or 0x0014 (write); all 31 also FAIL the Govee XOR checksum, and none carries a
      connection address. Bytes 9 and 11 are monotonic ~1 Hz counters and the 4-byte
      tail is high-entropy, so it is another BLE peripheral on the capturing phone
      whose payload coincidentally begins aa 01 0c. decode_govee._is_govee already
      rejects it on the checksum, so no decoder output was affected. There is no
      unmodelled long-form power reply to hunt.
    seq:
      - id: is_on
        type: u1
        doc: '[CONFIRMED_LIVE] raw power state, 0x00 off / 0x01 on. 0x01 was NOT witnessed until 2026-07-28, when a headless direct-mode write of 33 01 01 read back aa 01 01; every prior observation across the whole corpus was 0x00. That matters beyond filling a gap, because an all-zero body and a bare echo of the aa 01 query serialise to the identical 20 bytes (the same trap resolved for domain 0xa3, see this spec''s top doc), so no aa 01 reply before that write could distinguish a genuine state read-back from the device parroting the query. The 0x01 read settles it: the reply tracks stored power state. Restored to 0x00 afterwards.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  brightness_body:
    doc: |
      domain 0x04 whole-strip brightness read-back. Query aa 04 00 (all-zero body)
      -> reply aa 04 <percent>. The integration has always treated this domain as
      brightness (protocol.BRIGHTNESS_QUERY builds exactly this query, and
      coordinator stores the reply byte as brightness_pct), and the write side uses
      the same domain byte under the command header: 33 04 <percent> writes are
      captured at 20%, 8% and 1%.

      CORRECTION 2026-07-26. This body was briefly modelled as a "group count"
      because every captured reply carries 0x05 and the aa a5 read-back enumerates
      exactly five groups. That agreement is a coincidence. The replies are all 0x05
      because the lab strip is held at 5% under the approved 10% brightness limit,
      and a prior session decoded a checksum-valid
      aa 04 64 reply, which is 100 = 100% brightness, not a group count. Take this as
      a standing warning: a constant value that happens to match an unrelated known
      quantity is not attribution, and the shipped decoder should be consulted before
      a domain is renamed.

      THE WARNING WAS STILL LIVE IN OUR OWN TOOLING UNTIL 2026-07-29. govee_send.py
      labelled this domain "groups?" for three days after the correction, under a
      comment claiming its table was mirrored from decode_govee.py, which had said
      "brightness" the whole time. So every probe printed "reply groups?=5" while the
      canonical decoder disagreed, and a reader trusting the on-screen label would have
      read a group count off a brightness register. It was caught only because a crafted
      33 04 01 during the power-cycle session moved the read-back 5 -> 1 and then 1 -> 5
      on restore, which no group count does. Fixed in the same change. A correction that
      lands in the spec but not in the tool that prints the bytes is half a correction.
    seq:
      - id: brightness_pct
        type: u1
        doc: '[CONFIRMED_LIVE] whole-strip brightness percent (frame offset 2); raw percent, not 0..255 scaled. PROVEN TO TRACK 2026-07-26: with the strip driven from the app, the read-back returned 5 while the slider read 5% and 7 while it read 7%, across two separate device-page opens, and the matching writes were 33 04 05 / 33 04 07 / 33 04 03. Earlier corpus captures all read 0x05 only because the lab strip is pinned at 5%; 100 was observed historically. 0 in the query.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  unit_count_body:
    doc: |
      domain 0x40, a count of 15. Query aa 40 00 (all-zero body) -> reply aa 40 00 0f.
      Byte-identical in all 20 replies across the 14 corpus captures carrying a connect
      burst (re-derived 2026-07-27).
      THE VALUE IS SOUND, THE FIELD SPLIT IS NOT. 00 0f is equally a u2be holding 15
      and two bytes holding 0 and 15, and no capture separates them because the count
      never exceeds 255. Do not repeat the argument that a big-endian field would be
      unusual here: command_write::static_color.kelvin is a CONFIRMED_LIVE u2be on
      this same device, so endianness is not a tiebreak. Both bytes are therefore
      INFERRED, and the split stays open until a device reports a count above 255 or
      a non-zero byte appears at offset 2.
      WHAT THE 15 COUNTS IS NOT FULLY DETERMINED, but one reading is now dead and one
      is positively corroborated. On this strip the app's segment count, the 5 aa a5
      groups x 3 slots, and the IC count all equal 15, so this device alone separates
      nothing; the agreement is a coincidence of the hardware, not attribution.

      READING (a) "the app segment count" IS DEAD, on two models and neither of them
      this one, so it is recorded as the reason the old "IC / segment count" label was
      unearned rather than as an H617A fact:
        - ConsciousCode/govee_h7015 reads aa 40 -> 00 1e = 30 on a string light whose
          15 app segments are proven by an exhaustive per-bit bitmap sweep in its
          raw.log (bit 15 is shown to alias back to segment 0, so the count is 15 and
          not 16).
        - our own H6199 DreamView T1 reads aa 40 -> 00 26 = 38 (live 2026-07-27, direct
          read, see below), against the 15 segments egold555/Govee-Reverse-Engineering
          documents for that model.
      Two devices, both counting well past their app segment count.

      READING (b) "the live colour-buffer extent" IS CORROBORATED ON THIS DEVICE, and
      that part IS an H617A fact because it was measured here [CONFIRMED_LIVE
      2026-07-27]. aa a5 was read out past the five groups the app uses: groups 01..05
      return brightness+RGB in range (0x64 on fourteen slots, 0x1f on slot 1, matching
      this strip's actual retained paint), and groups 06..0a return data that is NOT
      colour, with leading bytes 0x73, 0x08, 0xfe, 0x00, 0x13, 0x45, 0xff, 0x0b, 0x01,
      i.e. outside the 0..100 brightness range the first five obey. So the colour
      region ends at group 05, the extent is 15, and it equals this count. The same
      boundary holds on the H7015, whose colour region runs 01..0a for an extent of 30
      against its own 0x40 of 30, and whose first non-colour body has the same shape as
      our group 06. See segments_body for the region boundary itself.

      READING (c) "the IC or physical LED count" IS UNTOUCHED and still co-varies with
      (b) on every device known, so (b) versus (c) is NOT settled. Two live strains on
      (b) to resolve before it is promoted:
        - the H6199's 38 is not a whole number of 3-slot aa a5 groups, so if (b) is
          right that model's colour region cannot be shaped like this one's;
        - the H7015's 30 also equals its plausible physical LED count (15 bulbs x 2
          beads, retail sourced and NOT capture-backed), which is exactly what (c)
          predicts too.

      A NOTE ON THE INSTRUMENT. The H6199 count was NOT obtainable by app-sniff: with
      the device connected over BLE and powered on, the vendor app sends only aa 01
      power polls and never asks aa 40, and never asks aa 04 either while still showing
      a brightness figure, so it is feeding that device's UI from its WiFi/cloud path.
      The value came from reading the register directly off the firmware. The H7015 app
      does not query 0x40 either. Absence of a query is therefore NOT evidence that a
      model lacks the register.

      THAT DIAGNOSIS IS NOW CONFIRMED, AND IT IS FIXABLE AT THE PHONE. Measured
      2026-08-03: with the iPhone in Airplane Mode and Bluetooth re-enabled, so the app
      had no IP path at all, the same device page immediately asked aa 04 and got
      brightness=30, and went on to ask aa 0f, aa 23, aa 12, aa 11, aa a9, aa ae, aa 35,
      aa 05 and four groups of aa a5 segment colours, none of which it had asked for
      minutes earlier over the same BLE link with WiFi up. The H6199 has no LAN API, so
      the app's only non-BLE route is Govee's cloud, and severing the phone's IP
      connectivity forces the whole UI onto the wire. Capture H6199 with the phone
      offline; a capture taken with WiFi up understates the protocol rather than
      revealing it. aa 40 was still not asked in that session, so the paragraph above
      stands for this register specifically.

      Our integration never reads this domain (segment count comes from a hardcoded
      ModelProfile), so the open label costs nothing.
    seq:
      - id: reserved
        type: u1
        valid: 0
        doc: '[INFERRED] frame offset 2; 0x00 in every query and every reply, 0x00 on the external H7015 reading, and 0x00 on the H6199 reading of 38. Either a reserved byte or the high byte of a u2be count; not separable, because no device yet observed counts past 255.'
      - id: count
        type: u1
        doc: '[INFERRED] frame offset 3; reads 15 on the H617A, 38 on the H6199 and 30 on the external H7015, so this is a genuine per-device varying count and not a protocol constant. PROVENANCE DIFFERS PER READING, and only the first is reproducible here: the H617A 15 is capture-backed 24 times over across 20 captures in the archive, every one from a single H617A, written here as D0:35:34:AA:BB:CC because the real address is rig identity and does not belong in a tracked spec; D0:35:34 is Govee''s OUI, which is the only part of it the reading depends on (swept 2026-07-29); the H6199 38 was read directly off the firmware register and is NOT in any capture, because as the type doc explains the vendor app never issues aa 40 to that model, so the two files named h6199-aa40* contain aa 01 polls and no aa 40 at all; the H7015 30 is external. Do not go looking for the 38 in the archive, and do not treat its absence there as a contradiction. The one-byte width is not corroborated by any of them, since a u2be over offsets 2..3 yields the same value. Deliberately named "count" rather than "segment_count": see the type doc for why naming it after segments asserts more than the captures show, and note the app segment count is now the one reading positively excluded.'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  colormode_body:
    doc: |
      domain 0x05 colour-mode read-back. The first body byte selects the mode; the
      following bytes mirror the matching write body for every mode EXCEPT static,
      where nothing is echoed and the byte that looks like the write-side sub is the
      33 a3 register instead (see cm_static). All four H617A mode selectors are seen live.

      protocol.parse_color_mode_response read static as a mirror until 2026-07-31,
      which invented an rgb of (0, 0, 0) whenever that register was set. It now takes
      the mirror as a per-model flag, defaulting to the behaviour proven here.
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

      SUB IS NOT A STATIC SUB-TYPE. IT MIRRORS THE 33 a3 FLAG. [CONFIRMED_LIVE
      2026-07-27g] Found by accident while testing what 33 a3 01 renders. Writing
      33 a3 01 moved this reply from aa 05 15 00 to aa 05 15 01, and restoring
      33 a3 00 moved it back, with no colour write in between. That is the first time
      this byte has ever been observed non-zero: every earlier capture read 0x00
      because nothing had ever set the a3 register while a static paint was showing.
      So the name inherited from the write side is wrong. Whatever
      command_write::multi_effect_cmd::flag is, this is its read-back inside the
      static mode window, and the two must be interpreted together.
    seq:
      - id: sub
        type: u1
        doc: '[CONFIRMED_LIVE] frame offset 3. NOT a static sub-selector: it mirrors the 33 a3 register. Observed 0x00 across every RGB set and CT set, then 0x01 immediately after writing 33 a3 01 and 0x00 again after 33 a3 00, with no colour write in between (strip-eyes block 2026-07-27). See this type''s doc and command_write::multi_effect_cmd.'
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
    doc: |
      group id then three segments of <brightness> <R> <G> <B> (aa a5 read-back).

      IT REPORTS THE RETAINED STATIC PAINT, NOT THE LIVE OUTPUT. [CONFIRMED_LIVE
      2026-07-27] Isolated by a clean before/after with an intervening mode change.
      Before: every segment read ff866b, the leftover of an earlier Color > Subsection
      test, with segment 1 at brightness 0x1f and the rest at 0x64. A More > Color
      Slider palette apply then wrote fifteen single-segment static colours, and
      afterwards aa a5 returned exactly that ramp (74ffff, 7df6f6, ... , ff7474) with
      segment 1 STILL at 0x1f, so brightness and colour are retained independently.
      A Light Up Your Life scene was then applied and left running: aa 05 reported
      colormode 0x04 code 0x284b, yet aa a5 kept returning the Color Slider ramp.
      So a running scene, DIY or music effect does NOT overwrite these bytes, and this
      read cannot be used to learn what the strip is currently showing. It is the
      static layer the device will fall back to.
      EXTENDED 2026-07-28 to the phone-microphone path: twenty a5 02 83 stream frames,
      driven with the device confirmed in music mode by aa 05 (0x13 0x06), moved these
      bytes not at all, across three separate colours. So the exclusion covers the
      mic-stream family too, and any probe hoping to see a stream frame render must use
      eyes on the strip. That run was designed against this very claim and wasted its
      positive control by ignoring it, which is the reason for spelling out the extra
      family here rather than leaving it implied.

      WHO READS IT. More > Snapshot List builds a saved state purely from reads, with
      no write at all: aa 05, then aa a5 groups 01..05, then aa a3. The snapshot is
      held app-side (the list is capped at 100 and was empty on this account), so
      nothing is stored on the device and there is no snapshot register to model.

      THE COLOUR REGION ENDS AT GROUP 05, AND THIS TYPE MODELS ONLY THAT REGION.
      [CONFIRMED_LIVE 2026-07-27] The app only ever asks 01..05, so nothing in the
      corpus showed what lies past it. Read directly, groups 06..0a DO answer, but not
      with colour: their leading bytes are 0x73, 0x08, 0xfe, 0x00, 0x13, 0x45, 0xff,
      0x0b and 0x01, well outside the 0..100 that every one of the fifteen real slots
      obeys. Group 06 came back 73 1f 6464 08 646464 fe 646464, which is the same shape
      as the first non-colour body on the H7015 (16 646464 08 646464 00 646464), a
      device whose colour region instead runs to group 0a. So the boundary is real and
      it moves with the device.

      This matters because the extent equals the aa 40 count on both devices (15 here
      over five groups, 30 there over ten), which is the positive evidence for the
      colour-buffer reading of that register. See unit_count_body.

      THE REGISTER HAS NO UPPER BOUND, AND IT REACHES LIVE STATE WELL OUTSIDE THE
      COLOUR REGION. [CONFIRMED_LIVE 2026-07-27c] A direct sweep asked groups 0b, 0c,
      0d, 0e, 0f, 10, 11, 12, 13, 14, 18, 1c, 20, 30 and ff. EVERY ONE ANSWERED; there
      is no silent boundary and no error frame anywhere in that range, so
      "aa a5 <group>" is not a bounded table lookup.

      THE WEEKDAY IS INDEX 10, NOT INDEX 5, AND INDEX 5 IS A CONSTANT.
      [CONFIRMED_LIVE 2026-07-28] This corrects a wrong attribution recorded on
      2026-07-27d, which read index 5 as 0x01 on a Monday and took the agreement with
      command_write::clock_cmd's Mon=1 convention as corroboration. That entry flagged
      its own weakness correctly (one day cannot separate a weekday from a constant)
      and a re-read on another day settled it the other way: on Tuesday 2026-07-28
      index 5 still read 0x01.
      Index 10 is the weekday, isolated by DRIVING it rather than waiting for the
      calendar. Crafted 33 09 writes moved it to exactly the value written, six times
      out of six, including 0x06 driven on a Tuesday, so the field is STORED verbatim
      and not derived by the device from its own calendar. The device's own untouched
      baseline independently read index 10 as 0x02 on Tuesday and 0x01 on Monday, which
      upholds Mon=1 from a second direction. Index 5 held 0x01 across every read on both
      days and across every written weekday, so it is positively excluded as the weekday
      and stays unexplained.

      INDEX 11 MIRRORS command_write::clock_cmd::flag1. [CONFIRMED_LIVE 2026-07-28]
      Proven with arbitrary non-binary values, which is what separates a mirror from a
      coincidence between two one-bit states: writing flag1 = 0x05 read back 0x05 and
      flag1 = 0x5a read back 0x5a, matching in 6 of 6 driven writes. So this byte is a
      read-back of a stored 8-bit register, not a constant. Its PURPOSE is still
      unknown, which is a separate question from where it lives; see clock_cmd::flag1.
      Note the UTC offset has no mirror in this body: writing its hour byte to 0x5a put
      no 0x5a anywhere here. Its mirror is in group 0x32 instead.

      GROUP 0x31 CARRIES A LIVE WALL CLOCK, and that, not the music match below, is what
      establishes the window reading. [CONFIRMED_LIVE 2026-07-27d] Body index 6 is the
      hour, index 7 the minute and index 9 the second. Isolated by a deliberate timed
      double-read against an otherwise untouched device: at host 17:26:46 it returned
      00030206 0001111a 00300101 (17:26:48) and at host 17:27:34 it returned
      00030206 0001111b 00250101 (17:27:37). Elapsed 48 s, clock advanced 49 s, the
      minute rolled 0x1a -> 0x1b exactly as the second wrapped, and EVERY OTHER BYTE
      HELD. So aa a5 reads live device state from an address space the vendor app never
      asks about, which is the capability the flat-window reading was really claiming.
      Hour, minute and second were re-confirmed on 2026-07-28 by crafted writes: the
      read-back returned each written time, which also makes this register the closed
      loop that any future clock experiment should verify against.

      Note this read-back is NOT a mirror of the clock_cmd body layout, which runs
      hour/minute/second/weekday/flag1/offset-hours/offset-minutes. Here a zero byte
      sits between minute and second, the weekday trails at index 10 and flag1 at
      index 11. Indices 0..3
      (00 03 02 06), 4, 5 and 8 held constant across every read taken on two separate
      days under crafted writes, and remain unexplained.

      GROUP 0x32 INDICES 1..2 MIRROR THE UTC OFFSET. [CONFIRMED_LIVE
      2026-07-28] The last clock_cmd body field without a read-back now has one, and it
      is in a DIFFERENT group from the other five. Sentinel-confirmed with a full round
      trip across three 27-group sweeps: baseline 0x0a, then 0x5a after writing
      utc_offset_hours = 0x5a, then 0x0a again after restoring. The sentinel appeared NOWHERE else
      in the window in any phase, so the attribution is unambiguous rather than a
      pattern match.

      [CONFIRMED_LIVE 2026-08-02] Changing the phone from Australia/Sydney (+10:00)
      to Australia/Adelaide (+09:30), then letting the vendor app reconnect, changed
      indices 1..2 from the Sydney shape 0a 00 to 09 1e. Restoring the phone to Sydney
      without reopening the app left 09 1e stored. This independently establishes the
      signed whole-hour offset and unsigned minute remainder as device state written
      during clock sync.

      THIS VINDICATES THE 0x30 RETRACTION BELOW. The probe was aimed at group 0x30
      index 7, which carries 0x0a and therefore agreed with the previously observed
      Sydney offset hour.
      That one-byte agreement was explicitly distrusted when the probe was designed,
      being weaker evidence than the three-byte run this same group had already produced
      and had retracted. The sentinel proved it a coincidence too: 0x30 did not move.
      Aim a probe with a coincidence if you like, but never conclude from one.

      WHAT MOVES IN THE WINDOW, RESTATED. The 27-group sweep below found exactly three
      movers under a passively observed device. Driving a register adds a fourth: with
      crafted clock writes, 0x31, 0x32, 0x34 and 0x35 moved and the other 23 groups were
      byte-identical across all three sweeps. So the window is not merely a clock and a
      counter; it also mirrors stored command-register state, and 0x32 only moves when
      something writes the register behind it. Note the asymmetry: the earlier sweep
      drove whole-strip brightness and a colour-mode change and saw nothing move, so
      not every register is mirrored here. Which ones are is an open question, and this
      window is now a proven instrument for asking it.

      THE MIRROR IS CLOCK-SPECIFIC, NOT A GENERAL REGISTER FILE. [CONFIRMED_LIVE
      2026-07-28] Worth stating plainly, because two mirrors in two different groups
      invites the reading that the window mirrors registers generally, and it does not.
      Both known mirrors belong to the SAME command register, 33 09. A sentinel probe
      wrote 0x5a into the sleep-timer (0x11) and then, separately, the wake-timer
      (0x12), each followed by a full 27-group sweep so a hit would be attributable to
      one register. The sentinel reached NO group in any of four sweeps, and outside
      0x31/0x34/0x35 not one byte moved. Both writes are known to have landed, because
      their own aa 11 / aa 12 read-backs returned the sentinel, so this is a real
      absence and not a write that silently failed. Together with the earlier sweep
      that drove brightness and colour-mode without moving anything, the window covers
      the clock register and the free-running counter, and nothing else yet found.
      It is therefore NOT available as a read-back instrument for arbitrary stuck
      constants, which was the hope when the clock-offset mirror turned up.

      THE MUSIC MATCH AT GROUP 0x30 WAS A COINCIDENCE, AND IS RETRACTED. Group 0x30
      returns 00000000 0005640a 00500701, embedding 05 64 0a, byte-for-byte the
      shiny_tail (style companion 05 64, then the constant 0x0a) of the music mode
      loaded when it was first read. That looked like the window landing on live music
      parameters. It is not. [CONFIRMED_LIVE 2026-07-27d] The body came back
      byte-identical across THREE independent changes to the very state it was supposed
      to mirror: a music -> DIY colour-mode change, a genuine music-mode change to
      Separation (33 05 13 32 63, aa 05 confirmed 0x13 0x32), and a Shiny Dynamic ->
      Calm style change (33 05 13 31 63 01, aa 05 confirmed 0x13 0x31), whose entire
      function is to select between the 05 64 and 14 46 companions. Not one byte moved.
      A 12-byte body containing a 3-byte run is a cheap coincidence, which is why it was
      recorded as a lead rather than a conclusion when found.

      The guard below therefore rests on the clock finding instead: a register with no
      bound, proven to return live non-colour state, will happily hand back anything.

      THE WINDOW IS OVERWHELMINGLY STATIC, AND WHAT MOVES IN IT IS TIME, NOT OUTPUT.
      [CONFIRMED_LIVE 2026-07-27e] A 27-group sweep (01..0c, 0f, 10, 18, 20, 2e, 2f,
      30..36, 40, ff) was read repeatedly over twelve minutes and five connections.
      EXACTLY THREE groups ever moved: 0x31, 0x34 and 0x35. The other twenty-four were
      byte-identical every time, across a whole-strip brightness change and a
      colour-mode change alike. Reads are passive: 36 consecutive queries moved nothing,
      which rules out a received-command counter and so protects the untouched-device
      framing that every read-only probe here depends on.
      REFINED 2026-07-28: that holds for a device being observed, but not for one being
      driven. Re-running the same 27-group list around a crafted clock write brought
      0x32 to life as well, so the correct statement is that three groups move on their
      own and a fourth moves when its register is written. See the group 0x32 note
      above.

      GROUPS 0x34 AND 0x35 HOLD ONE 32-BIT MILLISECOND COUNTER, SPLIT ACROSS THE GROUP
      BOUNDARY AS TWO 16-BIT LITTLE-ENDIAN HALVES. [CONFIRMED_LIVE 2026-07-27f] The low
      half is group 0x34 body indices 10..11; the high half is group 0x35 body indices
      1..2. Both are little-endian. It advances 1000 per second, so the low half wraps
      every 65.536 s and the whole field every 49.7 days.
        * THE TWO HALVES ARE ONE FIELD, AND THE HIGH HALF IS A WORD, NOT TWO BYTES.
          Across 53 rounds spanning four minutes, the ONLY bytes in group 0x35 that
          ever moved were indices 1 and 2; indices 0 and 3..11 were byte-identical in
          all 53 replies. That last clause is TRUE ONLY OF A FOUR-MINUTE WINDOW and was
          later shown to mislead: see the boot-scoped counters bullet below. Read as one
          little-endian 16-bit word those two bytes run
          1021, 1022, 1023, 1024, 1025 - consecutive, monotonic, no discontinuity.
          Read as two independent bytes the same data shows a spurious "carry event"
          at 0x03ff -> 0x0400 that is nothing more than a +1 crossing a byte boundary.
          Prefer the word reading: it has no special cases.
        * Endianness was settled by CROSS-RUN PREDICTION, not by fitting one run.
          Anchored on a single sample, the little-endian reading predicts every later
          read across 347 s and four separate connections to a mean error of 335 ms,
          the 1022 ms maximum being exactly the combined one-second quantisation of the
          counter and of the 0x31 clock used to time it. Big-endian gives a mean error
          of 15676 ms, which is noise. Read big-endian the field masquerades as two
          opposing ramps of -24 and +4 per second, which is the right number seen
          wrongly: 4*256 - 24 = 1000. Byte order here has flapped before, so prefer a
          prediction across runs to any within-run fit.
        * THE HIGH HALF ROLLS OVER EXACTLY WHEN THE LOW HALF WRAPS, OBSERVED DIRECTLY.
          [CONFIRMED_LIVE 2026-07-27f] A carry was predicted from an anchor and then
          watched happen. Anchored at device clock 19:39:42 with the field at
          65649415 ms, the low half was predicted to wrap 24 minutes later at 20:04:01;
          it was observed at 20:04:01, sampled every 4.6 s throughout. At that one
          sample body index 1 went 0xff -> 0x00 and body index 2 went 0x03 -> 0x04
          TOGETHER, which is what a single little-endian word does and not what two
          independent fields do. The reconstructed 32-bit value is continuous straight
          through: 67105431 -> 67110431, +5000 ms across 4.62 s, at the same rate as
          every other sample. A 24-bit reading of the same instant instead crashes
          16773783 -> 1567, and that contrast is the discriminating evidence.
          The rollover is ISOLATED, not merely correlated: six low-half wraps have now
          been caught in the act across two sessions (60997 -> 5481, 60150 -> 4629,
          64161 -> 2625, 62625 -> 2089, 62103 -> 1567, 61567 -> 31) and the high half
          incremented by exactly one at each, never between them. Reconstructed, the
          field tracks the independent 0x31 wall clock to within 1.03 s across twelve
          minutes and nine wraps.
        * IT IS UPTIME SINCE POWER-ON, PROVEN BY CUTTING THE POWER.
          [CONFIRMED_LIVE 2026-07-29] This paragraph used to say the opposite, and the
          reasoning it gave for doing so was sound: the field had never been seen near
          zero, and a notional zero merely CONSISTENT with an overnight power event is
          not evidence of one. The way to settle it was never a better fit to passive
          samples but an intervention, so mains power was cut for about fifteen seconds
          and restored. The field went from 79,547,895 ms (22.10 h) at 22:07:30 to
          86,314 ms (86.3 s) at 22:13:17. It counts milliseconds since the device last
          received power.
          THE ARITHMETIC WAS CHECKED AGAINST AN INDEPENDENT WITNESS rather than taken on
          its own word: 86.3 s before the 22:13:17 read puts power-on at 22:11:51, and
          the person at the strip reported plugging it back in in that minute. A second
          check runs the other way - the 60,821,387 ms read at 16:56 earlier the same day
          differs from the 22:07:30 read by 5.20 h against 5.18 h of wall clock, so the
          field had NOT reset in between and the strip had not silently lost power.
          Group 0x35 body indices 3..4 remain 0x00 in every reply ever captured, so
          whether the field is 32 bits or the low half of something wider is still not
          decidable, and nothing here depends on it.
        * AT LEAST TWO MORE BOOT-SCOPED COUNTERS SHARE GROUP 0x35, AND THE "ONLY INDICES
          1 AND 2 MOVE" CLAIM ABOVE IS A WINDOW ARTEFACT. [INFERRED 2026-07-29] The same
          power cut zeroed two further fields that four minutes of passive sampling had
          shown as byte-identical: read as little-endian words, indices 5..6 went 1380 to
          0 and indices 10..11 went 49 to 0. Both are far too slow to move inside a
          four-minute window, which is exactly why the earlier sweep concluded they were
          constant. Do not read that sweep as evidence of constancy for anything except
          the timescale it sampled.
          THIS IS ONE BEFORE-AND-AFTER PAIR AND NOTHING MORE. Their rates, widths and
          meanings are all unmeasured; 1380 and 49 against 22.10 h of uptime give no
          round unit and no ratio worth quoting. What the observation does establish is
          that group 0x35 carries SEVERAL boot-scoped counters rather than one, so a
          future sweep must span hours, not minutes, before calling any byte here fixed.

      IT DOES NOT TRACK RENDERING, AND THAT NEGATIVE IS THE POINT. [CONFIRMED_LIVE
      2026-07-27e] The counter was suspected of being live animation state, because
      sampled once a second under a running scene it ramps, floors and restarts exactly
      like a sawtooth. It is not. Writing a static paint of the colour the strip was
      ALREADY retaining (33 05 15 01 ff 88 0d, mask 7fff) stopped the animation while
      changing the visible output not at all, confirmed on the wire by aa 05 going
      0x04 scene 9 -> 0x15 -> 0x04 on restore. The counter ran at an unchanged rate
      throughout, with 0x31 interleaved as a control to prove the device was still
      answering with fresh data. So aa a5 offers NO way to observe what the strip is
      showing, and anything needing a render observable still needs a human looking at
      the light.

      WHOLE-STRIP BRIGHTNESS IS NOT MIRRORED HERE EITHER. [CONFIRMED_LIVE 2026-07-27e]
      A 5% -> 7% change, verified on the wire by aa 04, left all twenty-four static
      groups byte-identical, colour region 01..05 included. That independently upholds
      the retained-paint claim above: per-segment paint is held separately from
      whole-strip brightness. brightness_body remains the only read-back for it.

      NONE OF 0x31, 0x34 OR 0x35 IS MODELLED AS A TYPE, DELIBERATELY. Each is a couple
      of attributed bytes in a body whose remaining bytes are unexplained, and an
      unmatched switch-on or an unbounded field fails OPEN, not closed. Documenting the
      attribution costs nothing and claims nothing; modelling it would silently assert
      the rest.

      THE GUARD BELOW IS DELIBERATE. Without it this type parses group 06 quite happily
      and reports a segment at 115% brightness, which is a silent wrong answer of
      exactly the kind that has twice nearly become a finding. The group id is therefore
      range-checked so an out-of-region read FAILS LOUDLY instead. Whatever 06+ carries
      is not modelled here and needs its own type once it is understood.
    seq:
      - id: group
        type: u1
        valid:
          any-of: [1, 2, 3, 4, 5, 49, 50]
        doc: '[CONFIRMED_LIVE] raw group id. Only the modelled colour groups 01..05 and clock groups 0x31..0x32 are accepted. Direct reads prove groups 06+ answer with unrelated state, so accepting an unknown group as one of these layouts would be a silent wrong answer.'
      - id: segments
        type: segment
        repeat: expr
        repeat-expr: 3
        if: group >= 1 and group <= 5
        doc: '[CONFIRMED_LIVE] three 4-byte segment records'
      - id: clock
        type:
          switch-on: group
          cases:
            49: clock_group_31
            50: clock_group_32
        if: group == 49 or group == 50
        doc: '[CONFIRMED_LIVE] typed extended clock state for group 0x31 or 0x32'
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: '[CONFIRMED_LIVE] trailing zero padding to the 17-byte body window; grammar-enforced all-zero'
  clock_group_31:
    seq:
      - id: prefix
        size: 6
        doc: '[CONFIRMED_LIVE] six-byte opaque prefix held across timed reads and crafted clock writes'
      - id: hour
        type: u1
        valid:
          max: 23
        doc: '[CONFIRMED_LIVE] stored clock hour; isolated by timed reads and reproduced by crafted writes'
      - id: minute
        type: u1
        valid:
          max: 59
        doc: '[CONFIRMED_LIVE] stored clock minute; isolated by a live minute rollover and reproduced by crafted writes'
      - id: separator
        contents: [0x00]
        doc: '[CONFIRMED_LIVE] raw zero separator between minute and second in every group 0x31 reply'
      - id: second
        type: u1
        valid:
          max: 59
        doc: '[CONFIRMED_LIVE] stored clock second; isolated by timed reads and reproduced by crafted writes'
      - id: weekday
        type: u1
        doc: '[CONFIRMED_LIVE] stored weekday with Mon=1; moved across calendar days and followed crafted writes exactly'
      - id: flag1
        type: u1
        doc: '[INFERRED] stored mirror of command_write::clock_cmd::flag1, isolated with arbitrary sentinels; its purpose remains unknown'
  clock_group_32:
    seq:
      - id: prefix
        contents: [0x00]
        doc: '[CONFIRMED_LIVE] raw zero prefix before the UTC offset'
      - id: utc_offset_hours
        type: s1
        doc: '[CONFIRMED_LIVE] signed whole-hour UTC offset stored by app clock sync; changed from Sydney +10 to Adelaide +9 on 2026-08-02'
      - id: utc_offset_minutes
        type: u1
        valid:
          max: 59
        doc: '[CONFIRMED_LIVE] unsigned minute remainder of the UTC offset; changed from Sydney 0 to Adelaide 30 on 2026-08-02'
      - id: tail
        size: 9
        doc: '[CONFIRMED_LIVE] nine-byte opaque tail retained because no field inside it has been isolated'
  segment:
    seq:
      - id: brightness
        type: u1
        doc: '[CONFIRMED_LIVE] per-segment brightness percent. PROVEN TO TRACK 2026-07-28 headless: with segment 1 sitting at 0x1f and segments 2 and 3 at 0x64, writing 33 05 15 02 0a 01 00 (segment 1, 10 percent) moved aa a5 01 to 0a ff 00 00 while both the colour bytes and the other two records stayed byte-identical, then a write of 0x1f restored it exactly. Earlier corpus replies were all 0x64 because nothing had ever driven a single segment down.'
      - id: colour
        type: govee_common::rgb
        doc: '[CONFIRMED_LIVE] per-segment RGB (shared rgb type); held ff 00 00 across a brightness-only write, so brightness and colour are independently addressable'
  timer_body:
    doc: |
      aa 23 read-back: a 0xff table marker then four 4-byte scheduled-timer slot
      records, mirroring protocol.parse_timer_schedule_table. Live 2026-07-22:
      enabling slot 0 (07:30 Sunday, repeat 0xc0) read back 81 07 1e c0 with the
      enable bit 0x80 set, while the three disabled slots read 01 .. .. .. (enable
      bit clear, on-action bit set).

      THIS READ IS THE ONLY VERIFICATION 0x23 HAS. [CONFIRMED_LIVE 2026-07-27] The
      0x23 ack is a constant 33 23 00 00 .. that does not echo the write, so a
      schedule change is confirmed only here. Reading slot 2 immediately after writing
      it returned the written bytes verbatim, first ff 01 07 1e c0 01 09 10 80
      01 00 00 95 01 00 00 80 and then the same table with slot 2 back at 01 00 00 80
      once restored, which establishes that the device stores the repeat byte rather
      than the app merely remembering it.

      The table also cross-checks against the app's own Timer page, whose four rows
      read 7:30 Sunday, 9:16 do-not-repeat and two unset slots.
    seq:
      - id: marker
        contents: [0xff]
        doc: '[CONFIRMED_LIVE] raw 0xff table marker'
      - id: slots
        type: govee_common::timer_slot
        repeat: expr
        repeat-expr: 4
        doc: '[CONFIRMED_LIVE] four 4-byte scheduled-timer slot records (the slot index is positional 0..3)'
