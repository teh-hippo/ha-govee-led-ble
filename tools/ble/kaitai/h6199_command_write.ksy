meta:
  id: h6199_command_write
  title: Govee H6199 "33" command-write envelope (decode-only)
  endian: le
doc: |
  H6199 phone-to-light control write, modelled independently from the H617A
  command grammar. This root begins with the attributable iPhone capture
  h6199-aa40.pcap and deliberately imports no shared Govee types.

  The first captured H6199 write is the connect-time clock sync. Every one of its field
  names was inferred at first, on the rule that one frame cannot tell a field from a
  constant. A second clock capture on a different day and time has since moved the hour,
  minute, second and weekday, which is what named those four; the three bytes nothing has
  moved are still inferred, and are marked so below.

  TWO OPCODES ARE PROVEN ABSENT on this model, which is worth stating here
  because both are present in the vendor app for other SKUs and so will be found
  again by anyone reading it. 0x46 is the app's "reset device network", whose own
  confirm dialog string is str_clear_wifi, and 0x17 is the older provisioning-mode
  toggle. Neither is offered for the H6199 in the app, and neither is implemented
  by its firmware: measured 2026-08-04 over direct BLE, in single connections in
  which 0x01 and 0x04 both acknowledged either side of them and 0x46, 0x17 01 and
  0x17 00 drew nothing at all. That is the same control this project used to
  retire 0x41 on the H617A, and it is the reason there is no BLE route to clear
  this device's stored Wi-Fi credentials.
seq:
  - id: header
    contents: [0x33]
    doc: '[CONFIRMED_LIVE] H6199 command header at frame offset 0'
  - id: opcode
    type: u1
    enum: command_op
    doc: '[CONFIRMED_LIVE] H6199 command register at frame offset 1'
  - id: body
    size: 17
    doc: '[CONFIRMED_LIVE] H6199 command body at frame offsets 2..18; unmatched registers remain raw'
    type:
      switch-on: opcode
      cases:
        'command_op::power': power_body
        'command_op::brightness': brightness_body
        'command_op::mode': mode_body
        'command_op::schedule': schedule_body
        'command_op::clock': clock_body
        'command_op::display_setting': display_setting_body
        'command_op::relative_brightness': relative_brightness_body
  - id: checksum
    type: u1
    doc: '[CONFIRMED_LIVE] raw XOR checksum byte at frame offset 19; validated by the fixture runner'
enums:
  command_op:
    0x01: power
    0x04: brightness
    0x05: mode
    0x09: clock
    0x23: schedule
    0xa9: display_setting
    0xae: relative_brightness
  mode_sel:
    0x00: video
    0x04: scene
    0x15: static_colour
    0x13: music
  video_source:
    0x00: movie
    0x01: game
  video_region:
    0x00: part
    0x01: all
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
  music_mode:
    0x03: rhythm
    0x04: spectrum
    0x05: energetic
    0x06: rolling
  static_operation:
    0x01: colour
    0x02: brightness
types:
  rgb:
    seq:
      - id: red
        type: u1
        doc: '[CONFIRMED_LIVE] red channel; captured as 0xff for the palette swatch the app draws red'
      - id: green
        type: u1
        doc: '[CONFIRMED_LIVE] green channel; captured as 0xff for the swatch the app draws green'
      - id: blue
        type: u1
        doc: '[CONFIRMED_LIVE] blue channel; captured as 0xff for the swatch the app draws blue'
  power_body:
    seq:
      - id: is_on
        type: u1
        doc: '[CONFIRMED_LIVE] H6199 power state at frame offset 2; captured as 1 turning the light on and 0 turning it off from the same device page minutes apart'
      - id: opaque_tail
        size: 16
        doc: '[CONFIRMED_LIVE] remaining H6199 power-body bytes, captured as an opaque all-zero window'
  brightness_body:
    seq:
      - id: percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] H6199 brightness at frame offset 2, as a direct 0..100 percent
          rather than a 0..255 level. Captured 2026-08-03 in one session as 0x64, 0x33 and
          0x03 for a slider the app rendered as 100%, 51% and 3%, with nothing else touched
          between the three; each byte equals the displayed percent exactly, which no 0..255
          scaling reproduces.
      - id: opaque_tail
        size: 16
        doc: '[CONFIRMED_LIVE] remaining H6199 brightness-body bytes, captured as an opaque all-zero window'
  mode_body:
    seq:
      - id: sub_mode
        type: u1
        enum: mode_sel
        doc: |
          [CONFIRMED_LIVE] H6199 lighting-mode selector at frame offset 2. Register 0x05 is
          not a colour command: it multiplexes several modes on this byte, and only the
          static-colour case carries RGB.

          This was previously modelled as the first byte of an opaque 15 01 head, correctly,
          because every capture then held it constant and a value that never varies cannot be
          told apart from padding. Captures on 2026-08-04 varied it: 0x15 on a static-colour
          write, 0x13 selecting a music mode, 0x04 applying a saved DIY as a scene and 0x0a
          on the DIY editor's live apply, all from the same device page in the same sessions.
          Only the modes with a modelled payload are named in mode_sel; the DIY value 0x0a
          is observed but its body is not yet isolated, so it stays unnamed rather than
          guessed.

          A fifth value, 0x00, was captured later the same day from the video sheet, and it
          is worth saying that it is a mode selector and not an absence: the video body
          carries five settings after it. Zero is the value most easily mistaken for an
          unset byte, and here it names the model's headline feature.
      - id: detail
        size: 16
        doc: '[CONFIRMED_LIVE] H6199 mode payload at frame offsets 3..18; modes without an isolated body remain raw'
        type:
          switch-on: sub_mode
          cases:
            'mode_sel::video': video_body
            'mode_sel::scene': scene_body
            'mode_sel::static_colour': static_colour_body
            'mode_sel::music': music_body
  scene_body:
    doc: |
      Selects a scene by NUMBER. The scene's own definition is not in this frame: when the
      light does not already hold it, the app uploads the definition over 0xA3 first and
      this write is the reference that starts it. That upload is modelled separately, in
      h6199_effect_upload, whose kind byte separates a catalogue scene from a DIY effect.
    seq:
      - id: scene_id
        type: u2le
        doc: |
          [CONFIRMED_LIVE] the scene number, at frame offsets 3..4. Captured by applying
          scenes from the app's built-in gallery, Effects Lab, Workshop, AI generator and
          Light Up Your Life surface. Three adjacent tiles in the "House of the Dragon" row
          gave 16182, 16183 and 16184, differing at the low byte and the checksum alone;
          two adjacent "Natural" tiles gave 0 and 1. Consecutive numbers for adjacent tiles
          is what makes this an identifier rather than a pair of unrelated bytes.

          The high byte takes seven values across the committed corpus: 0x00, 0x01, 0x08,
          0x27, 0x29, 0x2c and 0x3f. Natural and Festival share 0x00, while the Gaming and
          Harmony Lab tabs share 0x08 across different categories. Light Up Your Life adds
          0x27 and 0x2c while scene_class remains 2. These comparisons establish the
          two-byte width and assign no further meaning to the high byte.

          Numbers are not dense within a category. The two "Sandbox 3D" scenes are 2178 and
          2200 and the two "Rain" ones 2237 and 2242, so the consecutive numbering seen in
          the gallery rows is a fact about those rows and not about the numbering
          everywhere. Whether the Effects Lab tiles were adjacent on screen was not
          recorded, so this does not yet contradict the adjacency argument above; a capture
          that walks one Lab category tile by tile would settle it.
          AN ID DOES NOT ALWAYS IDENTIFY AN EFFECT. Five effects applied from the app's
          Workshop produced this frame byte for byte, id 401 included, while uploading five
          different bodies of 153, 187, 34, 153 and 85 bytes. Four were the user's own saved
          effects and the fifth came from the community gallery behind Check Lighting Effects,
          so the slot is not particular to locally authored ones. For that id the upload
          carries the identity and the number selects the slot it just filled. Nothing in the
          frame distinguishes the five, and a reader treating a scene id as a key would
          conflate them.
      - id: scene_class
        type: u1
        doc: |
          [CONFIRMED_LIVE] a classifier for the scene, at frame offset 5, named for what it IS
          because nothing captured establishes what it MEANS. Committed fixtures carry three
          values: 1 on seven scenes, 2 on fourteen, and 0 on two AI-generated effects.

          IT IS NOT WHETHER THE LIGHT ALREADY HOLDS THE SCENE, which is what it was first
          named, on a correlation that held over fifteen captures: scenes written with 2 were
          preceded by an 0xA3 upload and scenes written with 1 were not. Two things killed
          that. The AI effects are uploaded exactly like catalogue ones, seven frames then
          five, yet carry 0. And applying one catalogue scene twice in a row, nothing else
          touched, reproduced the first write BYTE FOR BYTE and repeated the whole upload;
          had the byte meant what it was named, the second apply is where it changes.

          IT IS NOT REDUNDANT WITH THE ID, which for a while it appeared to be: every class-1
          id was below 10 and every class-2 id was 212 or above, so the byte was a function of
          the id on every fixture then committed and could have carried nothing of its own.
          Applying the gallery's "Sweet" settles that. Its id is 107 and its class is 1, and
          the two AI effects at 70 and 140 carry class 0, so a smaller id and a larger id both
          carry a DIFFERENT class than the one between them. No partition of the id range
          produces that, and the byte therefore carries information the id does not.

          IT IS ALSO NOT WHETHER A DEFINITION WAS UPLOADED, which was the last residue of the
          original reading still standing. Sweet is class 1 and is preceded by an 0xA3 upload,
          where the six other class-1 scenes are preceded by none.

          Two further readings remain live, both from the vendor Android app and so hints
          rather than evidence. One builds this position from the low byte of a scene's music
          code, which is 0 for a scene without music and would fit the AI values; against it,
          two gallery tiles from one row, one drawn with a music badge and one without, both
          carry 2. The other reads it as a scene type, and that app numbers its types static
          0, rgb 1, rgbic 2, graffiti 3, cube 4, diy 5, compose 6; against it, four effects
          composed in the app's own Workshop carry 2 rather than the 6 that numbering would
          predict.
      - id: opaque_tail
        size: 13
        doc: '[CONFIRMED_LIVE] remaining H6199 scene-body bytes at frame offsets 6..18, captured as an opaque all-zero window across all twenty-three scene fixtures'
  video_body:
    doc: |
      The DreamView T1's headline mode: a camera clipped to the television samples the
      picture and the strip follows it. Everything here is a SETTING for that mode. No
      per-frame colour stream appears on this link at all - the whole sheet was driven
      through its controls and the only writes were these, so the sampling and the mapping
      happen on the device.

      DO NOT PORT THIS LAYOUT TO ANOTHER MODEL, and not merely because the charter says so.
      The vendor app's encoder for the H6099 puts the picture profile at offset 3 and the
      region at offset 4 - the two the other way round from here - and writes the region as
      8 and 9 rather than 0 and 1. Every field below is pinned by a controlled comparison on
      THIS device, which is the only reason the assignment here is safe.
    seq:
      - id: region
        type: u1
        enum: video_region
        doc: |
          [CONFIRMED_LIVE] which part of the picture is followed, at frame offset 3. Captured
          2026-08-04 by tapping the app's "Part" and "All" tiles with nothing else touched;
          the two writes differ at this byte and the checksum alone, in both directions.
      - id: source
        type: u1
        enum: video_source
        doc: |
          [CONFIRMED_LIVE] the picture profile, at frame offset 4, which the app presents as
          a Game/Movie pair. Captured in the same session by tapping "Movie" with the region
          left on "All": that write differs from its Game counterpart at this byte and the
          checksum alone. Note the polarity, which is the opposite way round to the way the
          app lists them: Game is 1 and Movie is 0.
      - id: saturation
        type: u1
        doc: |
          [CONFIRMED_LIVE] colour saturation, at frame offset 5, as a direct 0..100 percent.
          Captured 2026-08-04 by dragging the Saturation slider inside the video sheet's
          Color Calibration panel: the byte read 0x58 while the panel showed 88% and 0x14
          while it showed 20%, matching the displayed percent exactly, with that byte and
          the checksum the only difference between the two writes.

          It sat unnamed until then, correctly, because every video write held it at 0x64
          while four other fields were varied deliberately. The control that moves it is not
          on the video sheet at all but one level down inside Color Calibration, which is
          worth recording: a byte that will not move is not always a constant, and is
          sometimes a control nobody has opened yet.

          NOTE THE PANEL LIES ABOUT ITS OWN STATE. Both this slider and the relative
          brightness one open reading 50% whatever the device is set to, so the opening
          reading is not a readback and must not be used as one.
      - id: sound_effects
        type: u1
        doc: |
          [CONFIRMED_LIVE] whether the strip also reacts to sound, at frame offset 6.
          Captured 2026-08-04 by switching the sheet's "Sound Effects" toggle on: the write
          differs from the preceding one at this byte and the checksum alone. Enabling it
          also reveals the softness control below, which is what makes the two fields a pair.
      - id: softness
        type: u1
        doc: |
          [CONFIRMED_LIVE] the "Softness" percentage that appears with sound effects, at
          frame offset 7. Captured by dragging that slider from full to near its low end in
          the same session: 0x64 became 0x0c, decimal 100 to 12, with this byte and the
          checksum the only difference. A direct percent, like brightness on this model,
          rather than a 0..255 level.
      - id: opaque_tail
        size: 11
        doc: |
          [CONFIRMED_LIVE] remaining H6199 video-body bytes at frame offsets 8..18, captured
          as an opaque all-zero window across every video write.

          THE FIRST BYTE OF THIS WINDOW IS ZERO FOR A REASON, NOT BECAUSE IT IS PADDING. The
          vendor app's video encoder writes seven payload bytes, through offset 8, and the
          seventh is a whole-strip relative brightness. It is written only on the Telink
          firmware branch; the other branch, which this unit takes, routes the same slider
          to register 0xae instead - which is why 0xae was captured at all and why this byte
          never moved. It is not named here because on this device it cannot be made to
          move, and a field nothing can vary is indistinguishable from padding. Recorded so
          that a unit on the other branch is not silently mis-parsed as having a longer tail.
  relative_brightness_body:
    doc: |
      How bright each EDGE of the strip is relative to the others, which is what makes a
      television backlight look even when the strip does not sit squarely behind the panel.
      A register of its own rather than part of the video body, though the app only offers
      it from the video sheet.
    seq:
      - id: unknown_head
        type: u1
        doc: |
          [CONFIRMED_LIVE] one byte at frame offset 2, captured as 0x01 in both writes and
          never seen to vary. Unnamed for that reason. Worth stating that it is NOT the
          count: the count sits after it, and reading this byte as the count is exactly the
          mistake the fixture runner caught, because 0x01 then truncates the payload to a
          single edge and the remaining three bytes vanish into the tail unnoticed.
      - id: edge_count
        type: u1
        doc: |
          [CONFIRMED_LIVE] how many edge values follow, at frame offset 3, captured as 4.
          Named a count rather than treated as padding because it equals both the number of
          bytes that then carry a percentage and the number of edges the sheet draws.
      - id: left_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] the left edge's relative brightness percentage, at frame offset 4.
          Captured 2026-08-05 by selecting ONLY the sheet's left edge and dragging its slider:
          this byte moved 0x5b -> 0x33, matching 91% -> 51%, while top, right and bottom
          stayed at their already-distinct 20%, 31% and 41%.
      - id: top_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] the top edge's relative brightness percentage, at frame offset 5.
          Captured by deselecting every edge, selecting ONLY the top edge and dragging the
          slider: this byte moved 0x5b -> 0x14, matching 91% -> 20%, while the other three
          bytes remained 0x5b. Restoring all four edges to 91% moved this byte back to 0x5b.
      - id: right_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] the right edge's relative brightness percentage, at frame offset 6.
          Captured by switching the selection from top to ONLY right and dragging the slider:
          this byte moved 0x5b -> 0x1f, matching 91% -> 31%, while the top remained 20% and
          left and bottom remained 91%.
      - id: bottom_percent
        type: u1
        doc: |
          [CONFIRMED_LIVE] the bottom edge's relative brightness percentage, at frame offset 7.
          Captured by switching the selection from right to ONLY bottom and dragging the
          slider: this byte moved 0x5b -> 0x29, matching 91% -> 41%, while the other three
          edge values did not move.
      - id: opaque_tail
        size: 11
        doc: |
          [CONFIRMED_LIVE] remaining bytes at frame offsets 8..18, captured as an opaque
          all-zero window in both writes.

          ITS FIRST TWO BYTES MAY NOT BE PADDING. The vendor app's encoder always emits six
          values here whatever the count byte says, the last two being a further pair of
          edges that a four-segment device does not have. Our bytes cannot tell that from
          four values followed by padding, because on this unit those two positions are zero
          under either reading, and no six-segment device is available to separate them. The
          count byte is therefore still what the payload length is taken from, and this note
          is here so the tail is not mistaken for spare room.
  display_setting_body:
    doc: |
      Two of the video sheet's settings share this opcode, and the second one is what showed
      it is not a flat body: white balance and blank-screen carry different payloads of
      different lengths behind a selector and a count. Modelled from one sample it looked
      like a fixed `0a 06` preamble; the reading survives, but as a value of the selector
      rather than as a constant.

      The same register is READ during the app's connect burst, as aa a9.
    seq:
      - id: setting
        type: u1
        enum: display_setting
        doc: |
          [CONFIRMED_LIVE] which display setting this write addresses, at frame offset 2.
          Captured 2026-08-04 as 0x0a from the "Blank Screen Settings" toggle and 0x00 from
          the white-balance strip inside Color Calibration, in one session on one sheet.
      - id: len
        type: u1
        doc: |
          [CONFIRMED_LIVE] how many payload bytes follow, at frame offset 3. Captured as 6
          for the blank-screen setting and 3 for white balance, and in both cases every byte
          beyond that count is zero and never moves while the bytes within it do. Two
          settings with different lengths is what tells a length apart from a second
          selector byte, which is all one sample could support.
      - id: payload
        size: len
        doc: '[CONFIRMED_LIVE] the setting-specific payload at frame offset 4; settings without a modelled body remain raw'
        type:
          switch-on: setting
          cases:
            'display_setting::white_balance': white_balance_payload
            'display_setting::blank_screen': blank_screen_payload
      - id: opaque_tail
        size: 15 - len
        doc: '[CONFIRMED_LIVE] the rest of the body, captured as an opaque all-zero window in every write of either setting'
  white_balance_payload:
    seq:
      - id: manual
        type: u1
        doc: |
          [INFERRED] set while white balance is being driven by hand, at frame offset
          4. Captured as 0x01 across the complete twenty-position strip and the Reset write.

          It was first modelled as an unnamed constant on exactly that evidence, which was a
          sampling artefact: every capture was taken with the manual strip, so the byte had
          no opportunity to move. It is named here on the vendor app's own encoder, which
          writes this position as the negation of an auto-white-balance flag. That is a hint
          and not a controlled comparison, and it is why the tag is inferred while every
          other field in this type is confirmed: the position and the value are
          capture-backed, the NAME is not. Settle it by turning Auto White Balance on and
          capturing.
      - id: red
        type: u1
        doc: |
          [CONFIRMED_LIVE] red gain, at frame offset 5. Every one of the app strip's twenty
          positions is committed, spanning 7 at the cool end to 21 at the warm end.
      - id: blue
        type: u1
        doc: |
          [CONFIRMED_LIVE] blue gain, at frame offset 6. Across all twenty positions it
          varies non-monotonically between 3 and 10, which a single 16-bit level could not
          explain.

          THESE TWO BYTES WERE BRIEFLY MODELLED AS ONE BIG-ENDIAN NUMBER, and the reasoning
          is worth keeping because it was wrong in an instructive way. The argument was that
          the pair rises monotonically with marker position read big-endian and does not
          read little-endian. That is true and it is not evidence: the app picks the pair
          from a bundled twenty-entry table sorted ascending by its FIRST column, so any
          reading that puts the first byte high is monotonic by construction. The rival
          reading the spec itself recorded - a value in the first byte and something else in
          the second - was the correct one.

          The app marker chooses an INDEX and writes the pair that index names; all twenty
          positions now match the table exactly. The firmware is less restrictive than the
          app: Home Assistant trials wrote (17,3), (17,4) and (16,4), and fresh aa a9
          replies returned each exact off-table or independently changed pair. The gains are
          therefore independent protocol fields even though the normal vendor UI follows a
          calibrated curve.

          It is still not colour temperature, but not for the reason first recorded: cool is
          (7, 10), blue-heavy, and warm is (21, 5), red-heavy, which is a gain pair.
  blank_screen_payload:
    seq:
      - id: is_on
        type: u1
        doc: |
          [CONFIRMED_LIVE] the blank-screen setting itself, at frame offset 4. Captured
          2026-08-04 by switching that toggle on and then straight back off: the two writes
          differ at this byte and the checksum alone, which is what tells a payload flag
          apart from a different setting under the same opcode.
      - id: opaque_tail
        size: 5
        doc: |
          [CONFIRMED_LIVE] the rest of the blank-screen payload, captured as 02 0a 00 78 00
          and identical in both writes.

          HELD OPAQUE, BUT NOT BECAUSE IT IS SHAPELESS. The vendor app's encoder writes this
          window as a flag followed by two little-endian 16-bit integers, which would make
          it 0x02, then 10, then 120. That reading accounts for every byte, and it explains
          something an earlier note here got half right: 0x78 was guessed to be a threshold
          or delay of 120, and 120 it is, but the trailing zero belongs to that number and
          there is a second integer of 10 in front of it that the guess did not see.

          It stays one window because not one of these five bytes has ever moved. Splitting
          it would name three fields on the strength of an encoder alone, and the whole
          point of separating them would be to say what they mean, which is exactly what is
          not known. Settle it by finding the controls behind the blank-screen sheet and
          driving them; the two integers should then separate on their own.
  music_body:
    seq:
      - id: mode
        type: u1
        enum: music_mode
        doc: |
          [CONFIRMED_LIVE] H6199 music mode at frame offset 3. Captured 2026-08-04 by tapping
          each of the app's four mode tiles in one session with the sensitivity slider and
          the sound-pickup toggle untouched, so the four frames differ in this byte alone.
          Energic, Rhythm, Spectrum and Rolling gave 0x05, 0x03, 0x04 and 0x06; re-tapping
          the first reproduced its frame byte for byte, so the write carries no sequence or
          timestamp.

          The app labels the first mode "Energic". The integration's slug is "energetic" and
          the two denote the same 0x05.
      - id: sensitivity
        type: u1
        doc: |
          [CONFIRMED_LIVE] H6199 music sensitivity at frame offset 4, written directly rather
          than scaled. Captured 2026-08-05 by dragging the app's Sensitivity slider with the
          mode and the sound-pickup toggle untouched: 99, 26 and 62, each write differing from
          the one before at this byte and the checksum alone, and then 100 and 1 by dragging
          hard to each end.

          THE RANGE IS 1 TO 100, which is neither of the two readings that were argued for.
          Ours said 0..100 and the vendor ANDROID app says 0..99, clamping with
          Math.min(value, 99) on both its write and its parse path. The iOS app this device
          is driven by writes 100 at the top, which Android cannot emit, and stops at 1 at
          the bottom rather than 0. So the two apps genuinely differ here and neither claim
          survived contact with the slider.

          Whether the firmware ACCEPTS 0 is untested and deliberately not asserted: all that
          is known is that this app will not send it. The same 1..100 floor appears on this
          model's relative-brightness slider, so it looks like a house convention rather than
          anything about this register.

          It sat INFERRED for two days on the reading that the slider could not be driven,
          which was true of the name-driven path and not of the app: the control is an
          unnamed element and the harness had no way to drag one. The note here proposed
          settling it by writing values from our own radio and reading back aa 05. That would
          have worked and it was the wrong experiment, because it tests our encoder against
          our own decoder. Teaching the harness to drag by coordinates within a named or
          measured rect settled it against the vendor app instead.

          THE SLIDER ONLY WRITES WHILE A MODE IS SELECTED. Dragging it on a freshly opened
          music page put nothing on the wire at all, which reads as a dead control rather
          than as a missing precondition.
      - id: is_calm
        type: u1
        doc: |
          [CONFIRMED_LIVE] which of the page's two reactivity profiles is chosen, at frame
          offset 5. Captured 2026-08-05 as 0 for Dynamic and 1 for Calm, by tapping one and
          then the other with everything else on the page untouched, so the pair differs at
          this byte and the checksum alone.

          Named for the value that is 1, because the app draws these as a two-position choice
          and nothing has been seen to take a third value. The vendor Android app writes this
          same position from a boolean, and separately initialises the field it comes from to
          16, which is a contradiction inside that source rather than in these bytes.
      - id: has_fixed_colour
        type: u1
        doc: |
          [CONFIRMED_LIVE] whether the user pinned a colour instead of letting the light pick
          one, at frame offset 6. Captured as 1 with the page's "Auto color" switch off and 0
          with it on, toggled straight back and forth: the two writes differ at this byte and
          the three colour bytes together, which is what makes the flag and the colour one
          decision rather than two.
      - id: fixed_colour
        type: rgb
        doc: |
          [CONFIRMED_LIVE] the pinned colour at frame offsets 7..9, meaningful only while the
          flag above is set. Captured as ff 00 00 and then 00 00 ff by choosing red and then
          blue from the palette that appears when auto colour is off, the two writes differing
          in these bytes alone. It reads 00 00 00 whenever the flag is clear.
      - id: opaque_tail
        size: 9
        doc: |
          [CONFIRMED_LIVE] remaining H6199 music-body bytes at frame offsets 10..18, captured
          as an opaque all-zero window across every music write.

          THIS WINDOW USED TO BE FIVE BYTES LONGER and was described the same way, which is
          worth recording because the reason it looked like padding was a sampling artefact:
          every music capture until then had been taken with auto colour on and the profile
          left alone, so four live fields sat at zero together. An all-zero window is evidence
          about the captures, not about the protocol.
  static_colour_body:
    seq:
      - id: operation
        type: u1
        enum: static_operation
        doc: |
          [CONFIRMED_LIVE] static-operation selector at frame offset 3. App colour and colour-
          temperature writes carry 0x01. Home Assistant trials on the H6199 carried 0x02 for
          masked segment brightness, and attributed aa a5 replies independently confirmed the
          requested percentages on one segment, a disjoint pair and all fifteen.
      - id: red
        type: u1
        if: operation == static_operation::colour
        doc: '[CONFIRMED_LIVE] H6199 red channel at frame offset 4; captured as 0xff for the Basic Colors red swatch and 0x00 for green and blue, in one session with nothing else touched'
      - id: green
        type: u1
        if: operation == static_operation::colour
        doc: '[CONFIRMED_LIVE] H6199 green channel at frame offset 5; captured as 0xff for the green swatch alone in the same session'
      - id: blue
        type: u1
        if: operation == static_operation::colour
        doc: '[CONFIRMED_LIVE] H6199 blue channel at frame offset 6; captured as 0xff for the blue swatch alone in the same session'
      - id: kelvin
        type: u2be
        if: operation == static_operation::colour
        doc: |
          [CONFIRMED_LIVE] colour temperature at frame offsets 7..8, big-endian. Captured on
          the H6199 as 2000, 5500 and 9000 K while dragging the app slider to its warm, middle
          and cool positions. Direct RGB writes carry zero.
      - id: preview
        type: rgb
        if: operation == static_operation::colour
        doc: |
          [INFERRED] RGB companion at frame offsets 9..11. It varied with each captured
          colour-temperature position and is zero on direct RGB writes, but its device-side
          role beside the independently encoded Kelvin value has not been isolated.
      - id: segment_mask
        type: u2
        if: operation == static_operation::colour
        doc: |
          [CONFIRMED_LIVE] H6199 segment selection at frame offsets 12..13, little-endian,
          bit 0 being the segment the app draws first. Captured 2026-08-03 by colouring one
          segment red, then a different segment the same red, then both together: 0x0001,
          0x0004, then 0x0005. The third write is what makes it a bitfield rather than an
          index or a count, because 0x0005 is the OR of the other two and no ordinal
          encoding produces it. A whole-strip write carries 0x7fff, fifteen bits set, which
          matches the fifteen segments the app draws.
      - id: opaque_tail
        size: 5
        if: operation == static_operation::colour
        doc: '[CONFIRMED_LIVE] remaining H6199 colour-body bytes at frame offsets 14..18, captured as an opaque all-zero window'
      - id: brightness_percent
        type: u1
        if: operation == static_operation::brightness
        doc: |
          [CONFIRMED_LIVE] direct segment-brightness percentage at frame offset 4. H6199
          trials used 17, 37 and 73, and aa a5 read-back reported the same values.
      - id: brightness_segment_mask
        type: u2
        if: operation == static_operation::brightness
        doc: |
          [CONFIRMED_LIVE] little-endian target mask at frame offsets 5..6. Trials addressed
          segment 1 (0x0001), segments 2 and 4 (0x000a), and all fifteen (0x7fff).
      - id: brightness_tail
        size: 12
        if: operation == static_operation::brightness
        doc: '[CONFIRMED_LIVE] remaining brightness-body bytes at frame offsets 7..18, captured as zero'
  clock_body:
    seq:
      - id: hour
        type: u1
        doc: '[CONFIRMED_LIVE] local hour; captured as 13 at 13:35 and as 9 at 09:54 in separate sessions'
      - id: minute
        type: u1
        doc: '[CONFIRMED_LIVE] local minute; captured as 35 and as 54 in those same two sessions'
      - id: second
        type: u1
        doc: '[CONFIRMED_LIVE] local second; captured as 21 and as 44, moving independently of the fields either side'
      - id: weekday
        type: u1
        doc: |
          [CONFIRMED_LIVE] ISO weekday, Monday being 1. Captured as 1 on Monday 2026-07-27
          and as 2 on Tuesday 2026-08-04. One sample could not tell a weekday from any other
          small constant; the second, on a known different day, is what names it.
      - id: flag1
        type: u1
        doc: '[INFERRED] unknown clock field, captured as 1 in both sessions and so still not distinguishable from a constant'
      - id: utc_offset_hours
        type: s1
        doc: |
          [INFERRED] apparent signed UTC-offset hour component; captured as +10 in
          Australia/Sydney both times. Still inferred rather than confirmed because both
          captures were taken in the same zone, so nothing has yet moved this byte. A
          capture with the phone on a different offset would settle it.
      - id: utc_offset_minutes
        type: u1
        doc: '[INFERRED] apparent UTC-offset minute component; captured as 0 in Australia/Sydney, unvaried for the same reason as the hours field'
      - id: opaque_tail
        size: 10
        doc: '[CONFIRMED_LIVE] remaining H6199 clock-body bytes, captured as an opaque all-zero window'
  schedule_body:
    seq:
      - id: slot
        type: u1
        doc: |
          [CONFIRMED_LIVE] which of the four schedule slots this write addresses, counting
          from zero. Captured as 0 and 1 by enabling the app's first and second timer rows
          with nothing else changed between them, which is what separates a slot index from
          a flag that happened to be zero.
      - id: flags
        type: u1
        doc: |
          [CONFIRMED_LIVE] schedule flags. Bit 0x80 marks the slot enabled and is set in
          every captured write, including the two that carried no time at all. Bit 0x01 is
          the action the slot performs: the byte read 0x80 while the app showed "Off" and
          0x81 after the same slot was switched to "On". The remaining bits have never been
          seen set and are deliberately not named.
      - id: hour
        type: u1
        doc: '[CONFIRMED_LIVE] hour the slot fires; captured as 0 for an untouched slot and 7 after setting 7:30'
      - id: minute
        type: u1
        doc: '[CONFIRMED_LIVE] minute the slot fires; captured as 0 and then 30 (0x1e) from the same edit'
      - id: repeat_mask
        type: u1
        doc: |
          [CONFIRMED_LIVE] repeat days, as 0x80 plus one bit per weekday from Monday at 0x01.
          Captured as 0x80 with no days chosen and 0x95 after choosing Monday, Wednesday and
          Friday, which is 0x80 | 0x01 | 0x04 | 0x10. That value matters: 0x80 on its own
          looks like a "fire once" flag, and 0x95 is the reading that rules it out by naming
          three days while keeping the same high bit.
      - id: opaque_tail
        size: 12
        doc: '[CONFIRMED_LIVE] remaining H6199 schedule-body bytes, captured as an opaque all-zero window'
