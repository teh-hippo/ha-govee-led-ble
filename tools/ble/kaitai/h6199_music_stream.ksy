meta:
  id: h6199_music_stream
  title: Govee H6199 phone-microphone music stream frame (a5 02 83, 7 bytes)
  endian: le
doc: |
  What the app pushes to the H6199 while Music is set to take its sound from the PHONE's
  microphone rather than the light's own. The phone does the listening and the colour
  choosing, and sends a colour per frame; nothing here describes an effect, only what to
  show right now.

  Modelled independently from the H617A frame of the same shape and importing nothing, per
  the charter. Every claim below is measured on 1662 H6199 frames, 266 of them distinct,
  captured  with the light off Govee's cloud so BLE was its only path. That the
  two models agree is an OBSERVATION here rather than an inheritance: nothing in this file
  was read across, and the checksum in particular was re-derived instead of assumed.

  THIS IS NOT A SHORT COMMAND FRAME. The 20-byte 0x33/0xaa envelope this model uses
  everywhere else carries an XOR checksum. This frame is seven bytes and carries the low
  eight bits of the SUM of the preceding six. On our own corpus sum-8 holds for 266 of 266
  distinct frames and XOR for 1 of 266, and that single agreement is a coincidence on one
  payload rather than a second valid reading. So the device accepts two checksum schemes,
  selected by opcode, and a frame that fails the usual one is not necessarily corrupt.

  That distinction is what makes these frames easy to miss entirely: a decoder that
  validates the XOR checksum before deciding whether a packet is Govee at all will discard
  every one of them, and the traffic then looks like a quiet link rather than like a stream
  it cannot read.
seq:
  - id: magic
    contents: [0xa5, 0x02, 0x83]
    doc: |
      the stream opcode at frame offsets 0..2, identical in all 266 distinct
      frames. Held as one literal rather than split into an opcode and a sub-code because
      nothing has ever varied any of the three, and where the boundary falls is a guess.
  - id: red
    type: u1
    doc: 'red channel at frame offset 3; 96 distinct values across the corpus, spanning 0 to 254'
  - id: green
    type: u1
    doc: 'green channel at frame offset 4; 109 distinct values, spanning 0 to 254'
  - id: blue
    type: u1
    doc: 'blue channel at frame offset 5; 120 distinct values, spanning 0 to 254'
  - id: checksum
    type: u1
    doc: |
      the low eight bits of the sum of frame offsets 0..5, validated by the
      fixture runner, which also refuses a corpus with no frame separating this scheme from
      XOR. Every fixture here is such a frame.

      The channels reach 254 and not 255 anywhere in the corpus. That is left unstated as a
      range because a ceiling nothing was driven against is not a measurement: the phone
      chose these values from whatever it heard, so 255 may simply never have come up.
