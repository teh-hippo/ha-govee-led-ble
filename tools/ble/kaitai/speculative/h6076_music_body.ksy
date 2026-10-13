meta:
  id: h6076_music_body
  title: Govee H6076 speculative companion-backed music body
  endian: le
  imports:
    - ../govee_common
    - ../govee_shared
    - h617a_control_payload
doc: |
  SPECULATIVE H6076, issue #343.
  Evidence source classes: a reporter's decrypted Android HCI snoop of the Govee
  app driving an H6076 (hardware 3.05.00, software 1.04.05, V1 encrypted
  session), which shows the Torch and Separation bodies in full, and Android
  Govee 7.5.30 producer code (straightfloorlamp/MusicModeV1.d,
  base2light/mode/music/bean/MusicEffect.toBytes and
  base2light/ble/controller/MultipleController4Music).
  Compatibility hypothesis: the app's default bodies for the five companion-backed
  effects other than Separation are the A3 command 0x41 body, a palette count and
  that many RGB triples, with no further field.  Separation appends the
  three-byte tail it shares with H617A: a split point, a fade flag and a speed
  byte that the app sets to 94 or 97 below 30 ICs and to 98 or 99 from 30, for
  fade on or off.  The selector that follows is described by h6076_music_write.ksy
  and the lamp's reply by h6076_music_ack.ksy.
  Skittles, Candy Crush, Fusion and Shiny were not captured in full.  Their bodies
  follow the Torch layout in the app producer code.  The reporter's separate LAN
  integration (scroom/ha-govee-local-segments) builds byte-identical bodies and
  reports that all twelve effects react on the lamp; that is plaintext replay, not
  a Bluetooth capture.
  Unresolved assumptions: the H6076's physical IC count, which decides the
  Separation speed byte beyond the captured 0x61 (fewer than 30 ICs, fade off),
  palette bounds per effect, the value of the unused bytes after the written
  fields, and the behaviour of firmware older than 1.02.00.
seq:
  - id: header
    type: govee_common::a3_header
  - id: command
    contents: [0x41]
  - id: mode
    type: u1
    enum: music_mode
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
  - id: tail
    size: tail_len
    type:
      switch-on: mode
      cases:
        'music_mode::separation': h617a_control_payload::separation_tail
  - id: padding
    size-eos: true
instances:
  tail_len:
    value: 'mode == music_mode::separation ? 3 : 0'
enums:
  music_mode:
    0x32: separation
    0x4d: skittles
    0x4e: candy_crush
    0x4f: fusion
    0x50: torch
    0x51: shiny
