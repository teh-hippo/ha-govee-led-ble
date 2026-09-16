meta:
  id: status_reply
  title: Govee H617A "aa" status-reply envelope (decode-only)
  endian: le
  imports:
    - govee_segment_page
    - govee_common
doc: |
  H617A 20-byte status reply. The final byte is the XOR of bytes 0 through 18.
  Segment replies have five groups of three records and four validated-zero bytes.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: aa_domain
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
        'aa_domain::segments': govee_segment_page(15, 3, true)
        'aa_domain::multi_effect': multi_effect_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
    0xa3: multi_effect
    0xa5: segments
  color_mode:
    0x15: static
    0x04: scene
    0x0a: diy
    0x13: music
types:
  multi_effect_body:
    doc: >
      Readback of the gradual-change boolean written by command_write opcode 0xa3. The
      value is persistent device state. H617A explicitly exposes no gradual-change
      capability, and paired physical comparisons found no visible behaviour for true.
    seq:
      - id: flag
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  power_body:
    seq:
      - id: is_on
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  brightness_body:
    seq:
      - id: brightness_pct
        type: u1
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  colormode_body:
    seq:
      - id: mode
        type: u1
        enum: color_mode
      - id: mode_body
        size: 16
        type:
          switch-on: mode
          cases:
            'color_mode::static': cm_static
            'color_mode::scene': cm_scene
            'color_mode::diy': govee_common::diy_selector
            'color_mode::music': govee_common::music_selector
  cm_static:
    doc: |
      The static-colour read-back. `sub`, then the colour temperature the device reports.

      `colour_temperature_kelvin` was `padding` with `valid: 0` until an H66A0 in
      colour-temperature mode answered `aa 05 15 00 0f a0 00...`. That failed the zero check,
      so the WHOLE frame was rejected, the colour-mode domain was never observed, and the
      device never completed a state refresh: its config entry sat in setup_retry reporting
      "unreachable at setup" while every other register answered normally on the same
      connection.

      Measured across two devices and arbitrary values, big-endian, matching the requested
      temperature exactly each time:

        asked 4000 K -> 0f a0   asked 6500 K -> 19 64   asked 3123 K -> 0c 33

      Confirmed independently from a capture of the vendor app, which is what settles it rather
      than any behaviour of this integration. The app's own read-back carries the same field --
      `aa 05 15 00 10 04` for 4100 K -- and its writes sweep the slider through the matching
      values: `33 05 15 01 00 00 00 0a 8c ...` = 2700 K, `0b b8` = 3000 K, `0e d8` = 3800 K,
      `19 64` = 6500 K. In the write the RGB sits at bytes 4-6 and the temperature at 7-8; in
      this read-back the temperature follows `sub`.

      **Zero means the device is not reporting one**, not 0 K. It reads zero in RGB mode on
      every device tested, and zero on an H61F5 even in colour-temperature mode: all three
      received a byte-identical `33 05 15 01 ...` carrying the same value, and only two echoed
      it back. The app lists both in `ColorTemConfig.isSupportColorTemMode`, so this is not a
      device that lacks the concept; it simply does not answer with a temperature here. Whether
      it holds one and declines to report it, or keeps it somewhere this register does not
      reach, is not established -- and it does not need to be. Where the field reads zero the
      temperature is recovered from the reported colour: the app inverts it through
      `KelvinHelp.color2kelvin`, testing whether the colour sits on the colour-temperature
      curve, which is the same thing this integration already does for a colour-temp state that
      reads back as its white point. That is
      why it set up fine while the other two did not.

      Anything after it stays opaque: nothing has ever been observed in those bytes.
    seq:
      - id: sub
        type: u1
      - id: colour_temperature_kelvin
        type: u2be
      - id: opaque
        size-eos: true
  cm_scene:
    seq:
      - id: scene_id
        type: u2le
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  version_body:
    seq:
      - id: text
        type: strz
        encoding: ASCII
      - id: padding
        type: u1
        valid: 0
        repeat: eos
  hw_version_body:
    seq:
      - id: prefix
        contents: [0x03]
      - id: text
        type: strz
        encoding: ASCII
      - id: padding
        type: u1
        valid: 0
        repeat: eos
