meta:
  id: h60a6_control
  title: H60A6 independent zone enablement and power-on behaviour
  endian: le
  imports:
    - h60a_bulk
doc: |
  SPECULATIVE H60A6 support for issue #402.  Compatibility hypothesis:
  independently writable panel/ring enable registers are available on Pact
  1/1, 1/2 and 1/3, independent of segmented-colour geometry.  EE30 reports
  master, panel and ring flags independently; only bit zero is interpreted.
  No master wake, sibling rewrite or illumination relationship is inferred.
  Power-on behaviour has three states, rather than a boolean memory setting.
  Other flag bits and suffixes are opaque.  Hardware capture qualification,
  other revisions and reply timing remain unresolved.
seq:
  - id: header
    contents: [0x33]
  - id: opcode
    type: u1
    enum: command
    valid:
      any-of: [command::zone_enable, command::power_on_behaviour]
  - id: body
    size: 17
    type:
      switch-on: opcode
      cases:
        'command::zone_enable': zone_command
        'command::power_on_behaviour': power_on_command
  - id: checksum
    type: u1
enums:
  command:
    0x30: zone_enable
    0x41: power_on_behaviour
  zone:
    0: panel_enabled
    1: ring_enabled
types:
  zone_command:
    seq:
      - id: zone
        type: u1
        enum: zone
        valid:
          any-of: [zone::panel_enabled, zone::ring_enabled]
      - id: enabled
        type: u1
        valid:
          any-of: [0, 1]
      - id: unknown_tail
        size: 15
  power_on_command:
    seq:
      - id: selector
        contents: [0x02]
      - id: state
        type: u1
        enum: h60a_bulk::power_on_state
        valid:
          any-of:
            - h60a_bulk::power_on_state::previous
            - h60a_bulk::power_on_state::on
            - h60a_bulk::power_on_state::off
      - id: unknown_tail
        size: 15
  zone_notification:
    seq:
      - id: header
        contents: [0xee, 0x30, 0x01]
      - id: total_flags
        type: u1
      - id: panel_flags
        type: u1
      - id: ring_flags
        type: u1
      - id: unknown_tail
        size: 13
      - id: checksum
        type: u1
    instances:
      is_on:
        value: (total_flags & 1) != 0
      panel_enabled:
        value: (panel_flags & 1) != 0
      ring_enabled:
        value: (ring_flags & 1) != 0
