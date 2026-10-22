meta:
  id: h617a_control_payload
  title: H617A generalised music tails and light-count payload
  endian: le
  imports:
    - ../govee_shared
doc: |
  SPECULATIVE H617A support work under capability umbrella issue #286;
  Fountain alternative geometry also relates to issue #129 (whose historical
  segment-count wording must not be interpreted as physical IC metadata).
  Hypothesis: Android 7.6.01 H617A music authoring uses the generalised
  mode-specific tails below.
  Existing H617A captures establish preset bytes and the palette-relative layout,
  not every representable value.  Newly variable Bloom no-rhythm speed, Shiny speed,
  Hopping speed/piece ranges, Piano speed/off-minimum, and Fountain piece length
  remain app-derived; alternate values and geometry need attributable official-app
  captures and owner qualification.  Other fields retain their existing captured
  values with app-derived semantic names.  Grouping tails here does not erase that
  evidence.
  H617E shares music_body's structural parser but keeps its independently declared
  pre-expansion presets, controls, and IC policy.  No new H617E qualification follows.
  H6099 uses its separate speculative/h6099_music_parameters schema and exact-model
  policy; shared app builders are evidence clues, not interchangeable SKU support.
  AA0F=15 was directly observed on H617A HW3.01.01/FW3.02.24, not in an official-app
  capture.  Its signed-positive boundary and ignored tail are app-derived.  Shared
  H617A-status-grammar consumers do not acquire exact-model count qualification.
  Count never establishes physical IC count or changes logical segment geometry.
  No full music-body readback, alternative IC geometry, or new rendering is qualified.
types:
  light_count_body:
    doc: |
      AA0F light-count reply body: the first payload byte is interpreted as a
      positive signed byte (1..127), stored separately from physical IC metadata,
      and queried with a zero-filled body.  Unconsumed bytes remain unknown.
      Diagnostic only.
    seq:
      - id: light_count
        type: u1
      - id: unknown
        size-eos: true
    instances:
      is_valid:
        value: light_count > 0 and light_count <= 127
  bloom_tail:
    doc: 'Bloom music tail; explicit styles set both speeds.'
    seq:
      - id: no_rhythm_speed
        type: u1
      - id: rhythm_speed
        type: u1
  shiny_tail:
    doc: 'Shiny music tail: minimum brightness, maximum brightness, and speed.'
    seq:
      - id: minimum_brightness
        type: u1
      - id: maximum_brightness
        type: u1
      - id: speed
        type: u1
  separation_tail:
    doc: 'Separation music tail; gradient speed depends on physical IC count.'
    seq:
      - id: point
        type: u1
      - id: gradient
        type: u1
      - id: speed
        type: u1
  hopping_tail:
    doc: 'Hopping music tail: background RGB, relative brightness, speed, and piece bounds.'
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
    doc: 'Piano Keys music tail; off_maximum = max(off_minimum, key_count / 2).'
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
    doc: 'Fountain music tail: start point, piece length, piece count, and speed.'
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
          difference and return to baseline.  The app derives 0x50 below 30 physical ICs;
          that threshold and alternative geometry remain unqualified.  Extreme 0xf0
          changed fill density, not evidence of linear speed scaling.
  day_and_night_tail:
    doc: 'Day and Night music tail; piece count is not logical segment count.'
    seq:
      - id: piece_count
        type: u1
      - id: speed
        type: u1
      - id: gradient
        type: u1
