meta:
  id: h7025_status_reply
  title: Govee H7025 basic and music status
  endian: le
  imports:
    - h6102_status_reply
    - h7025_music_write
doc: |
  SPECULATIVE H7025, issue #148.
  Android 7.6.01 h7020 NewDetailVM/Compose4InfoBle uses the shared switch,
  brightness and identity controllers, and Info4Detail dispatches AA05 mode
  15 to SubMode4Color and 13 to the H7025 music state. SubModeMusicV2 consumes
  only ID/sensitivity for new modes and flags/one RGB for Rhythm.
  Compatibility hypothesis: these basic fields share the modern AA envelope.
  Shared H617A command_write/status_query codecs provide power, percent
  brightness, AA0501, identity queries and whole-string 330515 colour writes;
  H7025 has fifteen bulbs and a 2700..6500 Kelvin range in h7020 Support.
  Color Config maps goods 296 to command version 0 and Kelvin type 1;
  Bytes.h emits RGB with a two-byte mask and Bytes.C uses direct white RGB
  for Kelvin. The exact profile overrides the shared builder's black default.
  Common payload imports do not inherit H6102's product capabilities.
  Unknown modes, suffixes and other domains stay opaque. No full palette
  readback or segment readback is claimed by this candidate.
  Unresolved: reporter hardware/firmware revisions, identity response encoding,
  response presence, RGB/Kelvin rendering and physical BLE qualification.
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
        'aa_domain::power': h6102_status_reply::power_body
        'aa_domain::brightness': h6102_status_reply::brightness_body
        'aa_domain::colormode': colormode_body
        'aa_domain::fw_version': h6102_status_reply::version_body
        'aa_domain::hw_version': h6102_status_reply::hw_version_body
  - id: checksum
    type: u1
enums:
  aa_domain:
    0x01: power
    0x04: brightness
    0x05: colormode
    0x06: fw_version
    0x07: hw_version
  color_mode:
    0x04: scene
    0x0a: diy
    0x13: music
    0x15: static
types:
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
            'color_mode::static': h6102_status_reply::cm_static
            'color_mode::scene': h6102_status_reply::cm_scene
            'color_mode::diy': h6102_status_reply::cm_diy
            'color_mode::music': h7025_music_write::music_selector
