meta:
  id: h617a_control_payload
  title: H617A generalized music tails and light-count payload
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H617A support work under capability umbrella issue #286;
  Fountain alternative geometry also relates to issue #129 (whose historical
  segment-count wording must not be interpreted as physical IC metadata).
  Hypothesis: Android 7.6.01 dreamcolorlightv1 UiV3/MusicFragmentV3 reaches the
  base2light/ble/music producers named below, including their generalized tails.
  Existing H617A captures establish preset bytes and the palette-relative layout,
  not every representable value. Newly variable Bloom no-rhythm speed, Shiny speed,
  Hopping speed/piece ranges, Piano speed/off-minimum and Fountain piece length
  remain APK-backed; alternate values/geometry need attributable official-app
  captures and owner qualification. Other fields retain their existing captured
  values with APK semantic names. Grouping tails here does not erase that evidence.
  H617E shares music_body's structural parser but keeps its independently declared
  pre-expansion presets, controls and IC policy. No new H617E qualification follows.
  H6099 uses its separate speculative/h6099_music_parameters schema and exact-model
  policy; common Java producers are evidence clues, not interchangeable SKU support.
  AA0F=15 was directly observed on H617A HW3.01.01/FW3.02.24, not in an official-app
  capture. Its signed-positive boundary and ignored tail are APK-derived. Shared
  H617A-status-grammar consumers do not acquire exact-model count qualification.
  Count never establishes physical IC count or changes logical segment geometry.
  No full music-body readback, alternative IC geometry or new rendering is qualified.
types:
  light_count_body:
    doc: |
      dreamcolorlightv1/ble/LightNumController.java:12-25 reads the first payload
      byte as a positive Java signed byte. adjust/v1/BleOpV3.java:374-383 stores
      it separately from IC metadata; :706-736 queries via a zero-body controller.
      Unconsumed bytes remain unknown. Diagnostic only.
    seq:
      - id: light_count
        type: u1
      - id: unknown
        size-eos: true
    instances:
      is_valid:
        value: light_count > 0 and light_count <= 127
  bloom_tail:
    doc: 'base2light/ble/music/RgbMusicZhanFang.java:17-24,51-85; explicit styles set both speeds.'
    seq:
      - id: no_rhythm_speed
        type: u1
      - id: rhythm_speed
        type: u1
  shiny_tail:
    doc: 'base2light/ble/music/RgbMusicCuiCan.java:18-25,48-76.'
    seq:
      - id: minimum_brightness
        type: u1
      - id: maximum_brightness
        type: u1
      - id: speed
        type: u1
  separation_tail:
    doc: 'base2light/ble/music/RgbicMusicFenLi.java:21-30,58-97; gradient speed depends on physical IC count.'
    seq:
      - id: point
        type: u1
      - id: gradient
        type: u1
      - id: speed
        type: u1
  hopping_tail:
    doc: 'base2light/ble/music/RgbicMusicYueDong.java:77-94,121-159.'
    seq:
      - id: background
        type: govee_shared::rgb
      - id: rel_brightness
        type: u1
      - id: speed
        type: u1
      - id: piece_length_min
        type: u1
      - id: piece_length_max
        type: u1
      - id: piece_count_min
        type: u1
      - id: piece_count_max
        type: u1
  piano_keys_tail:
    doc: 'base2light/ble/music/RgbicMusicGangQinJian.java:68-106,123-140; off-max = max(off-min, keys / 2).'
    seq:
      - id: gradient
        type: u1
      - id: key_count
        type: u1
      - id: speed
        type: u1
      - id: off_minimum
        type: u1
      - id: off_maximum
        type: u1
  fountain_tail:
    doc: 'base2light/ble/music/RgbicMusicDuiJi.java:41-76,88-106.'
    seq:
      - id: start_point
        type: u1
      - id: piece_len
        type: u1
      - id: piece_num
        type: u1
      - id: speed
        type: u1
        doc: |
          Existing H617A 0x10/0x50/0x10/0x50 comparison established a visible speed
          difference and return to baseline. APK derives 0x50 below 30 physical ICs;
          that threshold and alternative geometry remain unqualified. Extreme 0xf0
          changed fill density, not evidence of linear speed scaling.
  day_and_night_tail:
    doc: 'base2light/ble/music/RgbicMusicZhouYe.java:59-93,117-130; piece count is not logical segment count.'
    seq:
      - id: piece_count
        type: u1
      - id: speed
        type: u1
      - id: gradient
        type: u1
