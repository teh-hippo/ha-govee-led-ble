meta:
  id: music_stream
  title: Govee H617A phone-microphone music stream frame (a5 02 83, 7 bytes)
  endian: le
  imports:
    - govee_common
doc: |
  The frame the Govee app pushes when Music uses the PHONE's microphone instead of
  the device's. It is not a variant of the 20-byte command frame: it is shorter, it
  uses a different opcode, and it uses a DIFFERENT CHECKSUM ALGORITHM. It travels on
  the same ATT write characteristic (handle 0x0014) as every other write.

    a5 02 83 <R> <G> <B> <sum8>

  HOW IT WAS FOUND, AND WHY IT WAS INVISIBLE.
  Music > Sound Pickup Method > From mobile phone > Start Pickup. The capture showed
  1343 ATT operations but only 42 "Govee" packets, because decode_govee._is_govee
  validates the standard XOR checksum and every one of these frames failed it. The
  trailing byte is instead the low 8 bits of the SUM of the preceding six bytes,
  which held for 1237 of 1237 frames. The two algorithms are genuinely different and
  not merely coincident: a captured 33 05 15 static write checksums to 0xa7 under XOR
  and 0xaf under sum, and a5 02 83 0f 0f 00 checksums to 0x48 under sum and 0x24
  under XOR. So the device accepts two checksum schemes, selected by opcode.

  A whole-capture scan found this opcode in exactly ONE of the 61 pcaps we hold, the
  one that first exercised the phone-microphone path. It is therefore new evidence,
  not traffic we had been silently discarding all along.

  THE SUM-8 RULE, RE-MEASURED WITHOUT THE FILTER THAT USED TO SELECT FOR IT.
  The earlier count came from a scan that kept only frames
  whose sum-8 already verified, which cannot distinguish "every frame obeys the rule"
  from "the frames obeying the rule obey the rule". Re-run over every byte sequence
  matching the a5 02 83 prefix in s2-phonemic.pcap, s2-pickup-stop.pcap and
  h617a-mic-lifecycle-.pcap, with no checksum filter at all: 4682 candidates,
  4682 sum-8 valid, 0 valid under neither scheme, and 4681 in which the two schemes give
  different bytes so the frame actively separates them. Exactly one frame is valid under
  both, which is the coincidence you would expect and not a counter-example.

  NOTE WHAT THE GATE ACTUALLY RUNS. Sixteen anchors are committed under src/ and checked
  on every run; the 4682 figure above is provenance from the captures named, not a number
  the suite re-derives. The anchors were chosen to span the hue set and the amplitude
  envelope, including the all-zero-channel cases that make a naive checksum look right by
  accident, and all sixteen were confirmed present in those captures.

  WHAT THE PHONE ACTUALLY SENDS. The three payload bytes are a whole-strip RGB
  triple, streamed at almost exactly 20 Hz. The
  dedicated lifecycle capture measured 19.4, 20.1, 20.0 and 20.0 frames per second
  across four independent windows totalling 165 seconds and 3294 frames, so the rate
  is steady and source-independent. An earlier note in this file said "roughly 41 Hz
  (1237 frames in about 30 seconds)"; the frame count was right but the duration was
  an unmeasured estimate, and 1237 frames at the measured rate is 62 seconds, not 30.
  Corrected here rather than deleted, because a doubled rate is exactly the kind of
  number that gets copied into a capacity argument.

  The app does all the audio analysis and pushes finished colours; the device does no
  listening on this path and gets no mode, no palette and no sensitivity. Normalising
  each triple by its largest component yields exactly SEVEN hues across every capture:
  (1,0,0) red, (1,1,1) white, (1,1,0) yellow, (0,1,1) cyan, (0,1,0) green,
  (0,0,1) blue and (0.5,0,1) = 8b00ff violet. Each is scaled by an amplitude envelope
  that decays after a beat, e.g. red 254 -> 170 -> 86 -> 20 and cyan c7 -> 95 -> 64 ->
  32 -> 0f. No channel ever exceeded 0xfe across 3294 frames, so the envelope peaks one
  short of full scale. Hue selection and envelope shaping are app-side policy, not
  device behaviour, and nothing here should be read as a device capability.

  THE HUES ARE CHOSEN APP-SIDE, NOT DERIVED FROM THE MUSIC PALETTE.
  Isolated two independent ways. First, the on-device
  mode active throughout the lifecycle capture was Shiny, whose palette (music_body
  fixtures) is red/orange/yellow/green/blue: the stream carried white but never
  orange, so it cannot be reading that palette. Second and decisively, the phone
  pickup page carries an "Auto color" toggle. Turning it OFF collapsed the stream to a
  single hue (239 of 264 frames red, the remainder the decaying tail of the previous
  hue) and turning it back ON restored all seven, evenly distributed - while emitting
  ZERO frames of any kind on the wire for either toggle. An app-only control that
  changes the streamed colours proves the colour choice is app-side.

  THE PHONE-PICKUP PAGE HAS CONTROLS THIS SPEC DOES NOT MODEL. [CONFIRMED_LIVE
  2026-07-27b] Once Start Pickup is running the page exposes a Sensitivity slider, a
  multi-swatch colour bar, a Party / Dynamic / Calm style selector and the Auto color
  toggle above. Only Auto color has been exercised, and it sends nothing. The others
  are untested; since the whole path is app-side streaming, the working assumption is
  that they also send nothing and merely reshape the RGB the app computes, but that is
  an assumption and not a finding.

  RELATIONSHIP TO ORDINARY MUSIC MODE. This path REPLACES it rather than extending
  it. Selecting the phone as the source sends no BLE at all and does not tell the
  device to leave music mode; the app simply stops driving the on-device mode and
  starts streaming. The eleven on-device modes, their 0x41 A3 bodies (music_body.ksy)
  and the 33 05 13 selector (govee_common::music_selector) are all absent while
  streaming, and the UI hides them.

  THE STREAM OUTLIVES ITS OWN UI CONTROL, AND THE STOPPING TRIGGER IS NOW ISOLATED.
  A dedicated capture drove the whole lifecycle with
  timestamped marks. The results, in order:
    * Switching Sound Pickup Method to "From mobile phone" emits NOTHING. The stream
      begins 1.7 s after the separate "Start Pickup" tap, not at the method switch.
    * Switching the method back to "From device" restores the mode grid on screen and
      reports the device as the source, yet the stream CONTINUES, unchanged, at 20 Hz.
      It ran 1166 further frames over 58 s with no stop frame and no rate change. This
      reproduces the earlier report that it survived a navigation into another section:
      section navigation keeps you on the device page, so it never released anything.
    * Leaving the DEVICE PAGE ENTIRELY, back to the device list, stops the stream
      within 1.3 s. That is the trigger; the pickup-method control is not.
    * The iOS microphone indicator tracked the wire exactly: still lit after the method
      switch, gone after backing out. It remains the only trustworthy signal.
  Across the whole 209 s capture the ONLY non-stream Govee traffic was the aa 01 power
  keep-alive poll, so no explicit stop frame exists and the device simply holds the
  last colour it was sent. Practical consequence for anyone capturing: a capture taken
  any time after Start Pickup may be full of these frames with no on-screen indication,
  and an unrelated AI capture once held 12089 Govee packets that were almost all stream
  frames. Check for the opcode before reading anything into packet counts.

  NOT MODELLED HERE. A 2-byte notification on handle 0x0022 (values 0x0051 and
  0x0050 observed) is visible during the stream, and an earlier draft of this doc
  implied it was related. It is NOT. A corpus-wide scan
  found handle 0x0022 traffic in ALL 63 captures we hold, including ones recorded
  long before this opcode existed, so it belongs to some other service and has
  nothing to do with the stream. Corrected here rather than deleted, because the
  wrong version is the kind of claim that gets copied forward.

  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.
seq:
  - id: opcode
    contents: [0xa5]
    doc: |
      stream opcode 0xa5, constant across every captured frame, 3294 of them in the  lifecycle capture alone.
      It is a FOURTH opcode alongside 0x33 write, 0xaa read and 0xa3 multi-part write
      (see command_write.ksy for that set), and unlike those three it is checksummed
      by sum rather than XOR. Do not confuse it with the 0xa5 REGISTER read
      aa a5 <group>, which is the per-segment colour read-back in status_reply.ksy;
      that is a register number after the 0xaa read opcode, this is an opcode in the
      first byte, and the two are unrelated despite sharing a value.
  - id: stream_sub
    contents: [0x02]
    doc: |
      THE DEVICE DISPATCHES ON THIS BYTE, isolated . Constant 0x02 in
      every captured frame, which is only consistency; the byte was then isolated with
      eyes on the strip. A valid a5 02 83 frame rendered, a5 03 83 with this byte alone
      changed rendered NOTHING across 30 frames, and the valid frame rendered again
      afterwards, so the null is bracketed by working controls rather than resting on a
      strip that might have stopped listening. The device silently drops the frame.
      Meaning still not isolated: dispatched on is not the same as understood, and no app
      control moves it. Notably the Auto color toggle changes the streamed RGB without
      touching this byte.
  - id: stream_mode
    contents: [0x83]
    doc: |
      THE DEVICE DISPATCHES ON THIS BYTE, isolated  the same
      way as stream_sub and in the same session: a5 02 84, differing from a rendering
      frame by this byte alone, rendered nothing across 30 frames, between two valid
      frames that both rendered. Meaning not isolated. The high bit is suggestive of a
      flag but nothing separates 0x83 into fields, and the only surface that produces
      this frame offers no control that varies it: Auto color, which does change the
      payload, leaves this byte alone.

      NO MUSIC MODE IS REQUIRED TO RENDER A STREAM FRAME. The whole isolation ran with
      the strip in STATIC colour mode 0x15, confirmed by read before and after. This was
      a live confound going in, because both mic captures start mid-session with no
      mode-set in them, so nothing in the corpus could say whether the app had to enter
      music mode first. It does not.

      THE RENDER IS TRANSIENT AND SELF-REVERTING. The streamed colour appears during the
      burst and the strip returns to its retained paint on its own, with nothing written
      to restore it. That is why the  headless attempt was not-informative:
      aa a5 01..05 reports RETAINED per-segment paint, not live rendered output, so no
      read-back could ever have observed this. The instrument was wrong, not the question.
  - id: colour
    type: govee_common::rgb
    doc: |
      whole-strip RGB, the shared rgb type. Confirmed by the hue
      structure of the stream: every captured frame collapses to one of seven
      normalised hues under per-frame max-normalisation, each scaled by a decaying
      envelope, which is what a colour channel triple looks like and is not what three
      independent level or band bytes would look like. Re-confirmed on 3294 further
      frames in 2026-07-27b, where turning the app's Auto color toggle off collapsed
      the stream to a single hue: a control that selects a COLOUR moves these three
      bytes together, which is what a colour triple does and a level triple does not.
      There is no segment selector anywhere in the frame, so this paints the whole
      strip.
  - id: checksum
    type: u1
    doc: |
      low 8 bits of the arithmetic SUM of bytes[0..5], NOT the XOR
      used by every 20-byte frame. Valid on every captured frame, including all 3294 in the  lifecycle capture. See
      checksum_expected for the computed form.
instances:
  checksum_expected:
    value: '(0xa5 + 0x02 + 0x83 + colour.r + colour.g + colour.b) % 256'
    doc: |
      The checksum this frame should carry, recomputed from the payload. Kept as an
      instance rather than a `valid` clause so a decoder can compare and report a
      mismatch instead of failing the parse.
