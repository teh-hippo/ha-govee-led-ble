meta:
  id: h6199_effect_upload
  title: Govee H6199 reassembled 0xA3 effect body (decode-only)
  endian: le
doc: |
  The definition of a lighting effect, sent to the H6199 over the 0xA3 multi-frame channel
  and reassembled before it reaches this grammar. It is what the light is given when the app
  applies a scene the light does not already hold, immediately before the 33 05 04 write
  that starts it; see h6199_command_write::scene_body, whose scene_class byte took its first
  reading from whether one of these had been sent, a reading since retracted.

  Modelled independently from the H617A effect grammars and importing nothing, per the
  charter. That is not ceremony here: this model's DIY uploads were previously believed to
  use 0xA1 "in place of 0xA3", and every H6199 upload captured has used 0xA3, so the shared
  reading was already wrong about this family once.

  THREE SHAPES SHARE THIS ENVELOPE, chosen by the kind byte. A catalogue or Workshop scene
  arrives as a count and a list of length-prefixed blocks. An effect built in the app's DIY
  editor arrives as parameters - family, variant, speed and a palette. The two shipped
  builtin-parameter scenes carry a third body kind whose interior remains unmodelled.

  Workshop controls now account for the complete scene block: Applied Area, all four
  selection types and parameters, repeated Brightness sub-tabs, distribution, colour timing,
  counted RGB palette, movement and priority.

  The committed corpus spans catalogue scenes, Workshop layers, all nineteen DIY styles,
  repeated builtin-parameter scenes and repeated AI applications. The grammar accounts for
  every byte; only the non-adjustable builtin-parameter interior remains intentionally raw.
seq:
  - id: header
    contents: [0x01]
    doc: '[CONFIRMED_LIVE] effect-body marker at body offset 0, captured as 0x01 throughout the committed corpus'
  - id: chunk_count
    type: u1
    doc: |
      [CONFIRMED_LIVE] how many 17-byte transport chunks the body occupies, at body offset 1.
      Captured between 2 and 10, and in every case equal BOTH to the number of 0xA3 frames
      the phone actually sent and to the number of chunks the content needs, which is the
      used length divided by seventeen and rounded up. Two independent ways of arriving at
      the same number throughout the corpus is what names it.

      It is redundant with the transport, which is worth stating: the frame count is already
      knowable from the frames themselves, so this is the sender telling the light how much
      to expect rather than anything about the effect.
  - id: kind
    type: u1
    enum: body_kind
    doc: |
      [CONFIRMED_LIVE] which shape the rest of the body takes, at body offset 2. Captured as
      0x02 for scene-shaped uploads and 0x04 for the DIY editor, and the two shapes are not
      variations on each other: a scene body continues with a
      block count and a list of length-prefixed blocks, a DIY body with four parameters and
      a palette.

      This byte was first modelled as an unnamed constant, correctly, because the only
      bodies then captured were scenes and it never moved. The note left on it said a body
      that is not a scene is what would separate a version from a body type. That capture
      was then taken, and it did.

      A THIRD VALUE, 0x01, arrived from the gallery's "Sweet" and "Halloween-A". Both were
      reapplied and produced byte-identical uploads. Their bodies have different lengths and
      internal values, but two non-adjustable catalogue samples cannot isolate their fields,
      so this grammar recognises the shape without copying another model's layout into it.
  - id: content
    type:
      switch-on: kind
      cases:
        'body_kind::builtin_parameters': unmodelled_content
        'body_kind::scene': scene_content
        'body_kind::diy': diy_content
    doc: '[CONFIRMED_LIVE] the effect definition from body offset 3, in the shape the kind byte selects'
enums:
  body_kind:
    0x01: builtin_parameters
    0x02: scene
    0x04: diy
  effect_family:
    0x00: fade
    0x01: jumping
    0x02: twinkle
    0x03: marquee
    0x04: music
    0x08: chasing
    0x09: rainbow
    0x0a: crossing
  workshop_select_type:
    0x00: segment
    0x01: select_ic_continuously
    0x02: select_ic_randomly
    0x03: customize_segment
  brightness_order:
    0x00: brightest_darkest
    0x01: brightest_darkest_brightest
    0x02: darkest_brightest
    0x03: darkest_brightest_darkest
types:
  unmodelled_content:
    doc: |
      The builtin-parameter body shape, held whole. Sweet and Halloween-A are the complete
      shipped H6199 type-1 catalogue set and have different lengths, but neither is adjustable.
      Their repeat applications are byte-identical, so no controlled comparison can isolate
      an interior field without importing another model's grammar.
    seq:
      - id: opaque_body
        size-eos: true
        doc: '[CONFIRMED_LIVE] the entire body after the kind byte, captured from both shipped samples and their byte-identical repeats'
  scene_content:
    seq:
      - id: block_count
        type: u1
        doc: |
          [CONFIRMED_LIVE] how many blocks follow, at body offset 3. Captured from 1 through
          5, and in every case exactly that many length-prefixed blocks are present and
          consume the body up to its padding.
      - id: blocks
        type: block
        repeat: expr
        repeat-expr: block_count
        doc: '[CONFIRMED_LIVE] the effect definition, as block_count length-prefixed blocks starting at body offset 4'
      - id: padding
        size-eos: true
        doc: |
          [CONFIRMED_LIVE] zero padding out to the transport chunk boundary. Captured as 1 to
          16 bytes and always zero. Its length is whatever is left of the last seventeen-byte
          chunk, so the reassembled length cannot be used as the content length.
  diy_content:
    doc: |
      An effect the user built in the app's DIY editor, sent as parameters rather than as
      compiled blocks. Every field here is isolated through controlled editor comparisons.
    seq:
      - id: family
        type: u1
        enum: effect_family
        doc: |
          [CONFIRMED_LIVE] the animation family, at body offset 3. Captured as 0 for the three
          Fade styles, 1 for the two Jumping, 2 for the three Twinkle, 3 for the three
          Marquee, 4 for Music, 8 for the two Chasing, 9 for the two Rainbow and 10 for
          Crossing, by tapping each style in the editor's live-apply list with the palette and
          speed untouched.

          THE NUMBERING HAS GAPS, at 5, 6 and 7, and every family either side of them is
          present. So this is an identifier from a list longer than one model's editor offers,
          not a dense index over what this editor draws.

          The names are the labels the iOS app prints. The vendor ANDROID app calls family 2
          "Blinking" where iOS says "Twinkle", so these record one vendor's vocabulary rather
          than a protocol fact. Every capture in this repository comes from the iOS app, which
          is why its labels are the ones used.
      - id: variant
        type: u1
        doc: |
          [CONFIRMED_LIVE] which style within the family, at body offset 4. NOT AN ORDINAL,
          which is the whole reason this field is worth a note: the numbers are 0, 1, 2 for
          Fade1..3 and 0, 1, 2 for Twinkle1..3, which invites reading it as a zero-based
          index, but Jumping1 and Jumping2 give 0 and 2, skipping 1, and Marquee1..3 give 3,
          4 and 5 rather than starting at zero.

          Later captures make it plainer still. Chasing1 and Chasing2 give 9 and 10, Rainbow1
          and Rainbow2 give the SAME 9 and 10, and           Music1 gives 8, Music2 gives 6 and Music3 gives 7. So the value is not unique
          across families either: what identifies a style is the pair, and the number alone
          means nothing without the family beside it.
      - id: speed
        type: u1
        doc: |
          [CONFIRMED_LIVE] animation speed, at body offset 5. Captured as 0x32 and then 0x5c
          by dragging the editor's Speed slider with nothing else touched, the two uploads
          differing at this byte alone.
      - id: palette_len
        type: u1
        valid:
          expr: _ % 3 == 0
        doc: |
          [CONFIRMED_LIVE] how many palette bytes follow, at body offset 6. Captured as 21
          with the editor's seven default swatches and 18 after deleting one, three bytes per
          colour. Deleting a swatch moved this byte and removed exactly that colour's three
          bytes, which is what ties the count to the palette rather than to the body length.
      - id: palette
        type: rgb
        repeat: expr
        repeat-expr: palette_len / 3
        doc: '[CONFIRMED_LIVE] the colours the effect cycles, from body offset 7, in the order the editor draws them'
      - id: padding
        size-eos: true
        doc: |
          [CONFIRMED_LIVE] zero padding out to the transport chunk boundary, captured as
          between 6 and 18 bytes and always zero, across twenty-two DIY uploads spanning all
          nineteen styles, eight families and three palette sizes.

          A CLAIM THAT THIS IS ALWAYS PADDING WOULD BE TOO STRONG. The vendor Android app has
          a DIY encoder that appends a SECOND length-prefixed block after the palette, for
          effects carrying a direction or sub-effect list, and this field would swallow it
          silently while still validating. No captured H6199 upload contains one: Music2 and
          Music3 complete the editor's style list, and Music3 was also applied after shortening
          its palette. Every resulting tail is zero. So the field is right for everything this
          editor exposes, while a future firmware or editor surface could still add structure.
  rgb:
    seq:
      - id: red
        type: u1
        doc: '[CONFIRMED_LIVE] red channel; the editor default palette begins ff 00 00, which is the red swatch it draws first'
      - id: green
        type: u1
        doc: '[CONFIRMED_LIVE] green channel; the fourth swatch is 00 ff 00 and the app draws it green'
      - id: blue
        type: u1
        doc: '[CONFIRMED_LIVE] blue channel; the fifth swatch is 00 00 ff and the app draws it blue'
  brightness_block:
    doc: |
      One numbered Brightness sub-tab, six bytes in the order the editor displays its
      controls. Adding sub-tab 2 changed the parent count 1 to 2 and inserted exactly one
      further six-byte block before the distribution field.
    seq:
      - id: scope_high
        size: 1
        doc: '[CONFIRMED_LIVE] Brightness Scope upper handle, scaled to 0..255; moving 100% to 80% changed ff to cd alone'
      - id: scope_low
        size: 1
        doc: '[CONFIRMED_LIVE] Brightness Scope lower handle, scaled to 0..255; moving 0% to 35% changed 00 to 5b alone'
      - id: order
        type: u1
        enum: brightness_order
        doc: '[CONFIRMED_LIVE] Brightness Order: 0 Brightest-Darkest, 1 Brightest-Darkest-Brightest, 2 Darkest-Brightest, 3 Darkest-Brightest-Darkest'
      - id: change_speed
        size: 1
        doc: '[CONFIRMED_LIVE] Brightness Changing Speed, scaled to 0..255; 50% is 80 and 93% is ed'
      - id: retention_brightest
        size: 1
        doc: '[CONFIRMED_LIVE] Retention Time of the Brightest Light, written directly'
      - id: retention_darkest
        size: 1
        doc: '[CONFIRMED_LIVE] Retention Time of the Darkest Light, written directly'
  block:
    doc: |
      One scene or Workshop layer. The record length is fully accounted for by the
      selection header, repeated Brightness blocks, colour palette and fixed movement
      trailer. Captured record lengths 26 through 47 all consume without residue.
    seq:
      - id: len
        type: u1
        doc: '[CONFIRMED_LIVE] the block length, not counting itself; captured between 26 and 47'
      - id: applied_area
        type: u1
        doc: |
          [CONFIRMED_LIVE] Applied Area at block offset 0. The high nibble is the width in
          tenths and the low nibble is the start: moving [0,4] to [0,5] changed 40 to 50,
          then moving the lower handle to 1 changed 50 to 41.
      - id: select_type
        type: u1
        enum: workshop_select_type
        doc: |
          [CONFIRMED_LIVE] Select Type at block offset 1: Segment 0, Select IC Continuously
          1, Select IC Randomly 2 and Customize Segment 3.
      - id: select_param_1
        type: u1
        doc: |
          [CONFIRMED_LIVE] first Select Type parameter at block offset 2. It is the random
          Maximum ICs, isolated 2 to 3; Customize Segment displayed 1 here.
      - id: select_param_2
        type: u1
        doc: |
          [CONFIRMED_LIVE] second Select Type parameter at block offset 3. It follows Number
          of Segment/IC and random Minimum IC; Customize Segment displayed 0 here.
      - id: layer_flags
        type: u1
        doc: |
          [CONFIRMED_LIVE] layer flags at block offset 4. Bit 0x02 selects Brightness
          Gradient rather than Unified, isolated by changing 0x12 to 0x10 alone. Other bits
          remain raw.
      - id: brightness_block_count
        type: u1
        doc: |
          [CONFIRMED_LIVE] number of six-byte Brightness sub-tabs. Adding tab 2 changed this
          byte from 1 to 2 and increased the record length from 29 to 35.
      - id: brightness_blocks
        type: brightness_block
        repeat: expr
        repeat-expr: brightness_block_count
        doc: '[CONFIRMED_LIVE] brightness_block_count six-byte Brightness sub-tabs'
      - id: distribution_direction
        type: u1
        doc: |
          [CONFIRMED_LIVE] packed Distribution Method and general Direction. Bit 0x80 means
          Backward. With Forward held constant, Unified Colour is 0, Based on Number of IC
          is 1 and Based on Segment is 2.
      - id: colour_change_speed
        size: 1
        doc: '[CONFIRMED_LIVE] Color Changing Speed, scaled to 0..255; 50% is 80 and 92% is ea'
      - id: retention_time
        size: 1
        doc: '[CONFIRMED_LIVE] colour Retention Time, written directly'
      - id: colour_count
        type: u1
        doc: |
          [CONFIRMED_LIVE] number of RGB palette entries. Deleting one of two colours changed
          this byte from 2 to 1 and shortened the record by exactly three bytes.
      - id: palette
        type: rgb
        repeat: expr
        repeat-expr: colour_count
        doc: '[CONFIRMED_LIVE] colour_count ordered RGB triplets from the Workshop palette'
      - id: selected_movement
        type: u1
        doc: |
          [CONFIRMED_LIVE] packed selected-area movement byte. Bit 0x10 enables movement,
          bit 0x04 enables Enter and Exit Effect, and direction values are Forward 0,
          Forward and Backward 1, Backward 2 and Backward and Forward 3.
      - id: selected_movement_interval
        size: 1
        doc: '[CONFIRMED_LIVE] selected-area Moving Interval, written directly'
      - id: selected_movement_speed
        size: 1
        doc: '[CONFIRMED_LIVE] selected-area Moving Speed, scaled to 0..255'
      - id: overall_movement
        size: 1
        doc: |
          [CONFIRMED_LIVE] packed Overall Moving Effect enable and direction, fixed four
          bytes from the record end
      - id: overall_movement_interval
        size: 1
        doc: '[CONFIRMED_LIVE] overall Moving Interval, written directly'
      - id: overall_movement_speed
        size: 1
        doc: '[CONFIRMED_LIVE] overall Moving Speed, scaled to 0..255'
      - id: layer_priority
        size: 1
        doc: '[CONFIRMED_LIVE] Effect Layer Priority at the final record byte, 0 or levels 1 through 5'
      - id: excess
        size: 'len - 17 - brightness_block_count * 6 - colour_count * 3'
        doc: '[CONFIRMED_LIVE] bytes not consumed by the complete record grammar; empty in every fixture'
    instances:
      applied_area_width_tenths:
        value: '(applied_area & 0xf0) >> 4'
        doc: '[CONFIRMED_LIVE] Applied Area width in tenths'
      applied_area_start_tenths:
        value: 'applied_area & 0x0f'
        doc: '[CONFIRMED_LIVE] Applied Area start in tenths'
      brightness_is_gradient:
        value: '(layer_flags & 0x02) != 0'
        doc: '[CONFIRMED_LIVE] Brightness is Gradient when layer_flags bit 0x02 is set'
      brightness_scope_low:
        value: 'brightness_blocks[0].scope_low'
        doc: '[CONFIRMED_LIVE] compatibility view of the first Brightness block lower scope'
      brightness_change_speed:
        value: 'brightness_blocks[0].change_speed'
        doc: '[CONFIRMED_LIVE] compatibility view of the first Brightness block changing speed'
      retention_time_brightest:
        value: 'brightness_blocks[0].retention_brightest'
        doc: '[CONFIRMED_LIVE] compatibility view of the first Brightness block brightest retention'
      retention_time_darkest:
        value: 'brightness_blocks[0].retention_darkest'
        doc: '[CONFIRMED_LIVE] compatibility view of the first Brightness block darkest retention'
      distribution_method:
        value: 'distribution_direction & 0x7f'
        doc: '[CONFIRMED_LIVE] Distribution Method value'
      direction_is_backward:
        value: '(distribution_direction & 0x80) != 0'
        doc: '[CONFIRMED_LIVE] general Direction is Backward when bit 0x80 is set'
      selected_movement_enabled:
        value: '(selected_movement & 0x10) != 0'
        doc: '[CONFIRMED_LIVE] selected-area movement is enabled when bit 0x10 is set'
      selected_enter_exit_enabled:
        value: '(selected_movement & 0x04) != 0'
        doc: '[CONFIRMED_LIVE] Enter and Exit Effect is enabled when bit 0x04 is set'
      selected_direction:
        value: 'selected_movement & 0x03'
        doc: '[CONFIRMED_LIVE] selected-area direction value'
