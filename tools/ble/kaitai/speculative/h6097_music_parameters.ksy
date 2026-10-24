meta:
  id: h6097_music_parameters
  title: Govee H6097 onboard music companion
  endian: be
  imports:
    - ../govee_shared
    - h6097_music_write
    - h6099_music_parameters
doc: |
  SPECULATIVE H6097 support for issue #431.  A3/41 carries mode, palette and
  these mode-specific tails before selector activation.  Shared tail structures
  are compatible with H6099, but Energetic independently carries two opaque
  parameter bytes (default 01 00).  Physical IC count is independent of the
  fourteen logical zones.  Parameter rendering, Energetic byte semantics and
  firmware differences remain unqualified.
seq:
  - id: mode
    type: u1
    enum: h6097_music_write::music_mode
  - id: num_palette
    type: u1
  - id: palette
    type: govee_shared::rgb
    repeat: expr
    repeat-expr: num_palette
  - id: tail
    type:
      switch-on: mode
      cases:
        'h6097_music_write::music_mode::energetic': energetic_tail
        'h6097_music_write::music_mode::bloom': h6099_music_parameters::bloom_tail
        'h6097_music_write::music_mode::shiny': h6099_music_parameters::shiny_tail
        'h6097_music_write::music_mode::separation': h6099_music_parameters::separation_tail
        'h6097_music_write::music_mode::hopping': h6099_music_parameters::hopping_tail
        'h6097_music_write::music_mode::piano_keys': h6099_music_parameters::piano_tail
        'h6097_music_write::music_mode::fountain': h6099_music_parameters::fountain_tail
        'h6097_music_write::music_mode::day_and_night': h6099_music_parameters::daynight_tail
enums:
  companion_mode:
    0x05: energetic
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
types:
  energetic_tail:
    seq:
      - id: unknown_parameters
        size: 2
