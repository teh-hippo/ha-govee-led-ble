meta:
  id: h6076_music_write
  title: Govee H6076 speculative music selector write
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H6076, issue #343.
  Evidence source classes: a reporter's decrypted Android HCI snoop of the Govee
  app driving an H6076 (hardware 3.05.00, software 1.04.05, V1 encrypted
  session) and Android Govee 7.5.30 producer code
  (straightfloorlamp/MusicModeV1.d, straightfloorlamp/ble/SubModeMusicV2.getWriteBytes,
  straightfloorlamp/pact/Support.isSupportNewMusicMode).  The capture is
  reporter-supplied and its raw file has not been reviewed, and no integration or
  owner BLE test of an H6076 exists yet.
  Compatibility hypothesis: the H6076 writes its music selector at submode 0x0f,
  not the H617A submode 0x13.  The twelve-effect screen applies to software
  1.02.00 or newer on pact 1/1 or 2/1; older software uses a legacy screen that
  reuses the same submode with fewer effects.  The six legacy effects carry their
  parameters in the selector.  Rhythm has a leading dynamic byte.  The
  companion-backed effects carry only the sensitivity and take their palette from
  the preceding A3 body described by h6076_music_body.ksy.
  Unresolved assumptions: the value of the unused bytes after the written fields
  (the capture lists frames before padding), whether a fixed-colour flag other
  than one is accepted, whether the device echoes the selector, and the behaviour
  of firmware older than 1.02.00.  The final byte is the XOR of bytes 0 through 18.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    contents: [0x05]
  - id: sub
    contents: [0x0f]
  - id: selector
    size: 16
    type: music_selector
  - id: checksum
    type: u1
enums:
  music_mode:
    0x00: energetic
    0x02: hopping
    0x04: rhythm
    0x06: beat
    0x07: spray
    0x08: bounce
    0x32: separation
    0x4d: skittles
    0x4e: candy_crush
    0x4f: fusion
    0x50: torch
    0x51: shiny
types:
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        doc: The app slider runs from 0x00 to 0x63.
        type: u1
      - id: settings
        size: 14
        type:
          switch-on: mode_id
          cases:
            'music_mode::rhythm': rhythm_settings
            'music_mode::energetic': colour_settings
            'music_mode::hopping': colour_settings
            'music_mode::beat': colour_settings
            'music_mode::spray': colour_settings
            'music_mode::bounce': colour_settings
            _: opaque_settings
  rhythm_settings:
    seq:
      - id: dynamic
        doc: One is Dynamic and zero is Calm.
        type: u1
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: padding
        size-eos: true
  colour_settings:
    seq:
      - id: has_fixed_colour
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: has_fixed_colour != 0
      - id: padding
        size-eos: true
  opaque_settings:
    seq:
      - id: padding
        size-eos: true
