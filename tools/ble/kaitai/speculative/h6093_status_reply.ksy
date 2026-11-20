meta:
  id: h6093_status_reply
  title: H6093 projection power and compatible basic status
  endian: le
  imports:
    - h600a_status_reply
doc: |
  SPECULATIVE: partial exact-model status contract. AA34, AA04, AA05, AAEF,
  EE20 and EE30 envelopes are recorded on Pact 2/1, hardware 3.03.02 and
  firmware 1.00.16; other revision details remain unconfirmed.
  AA34 carries the projection-power flag independently of speaker playback.
  Brightness, mode, firmware and hardware retain their compatible basic
  envelopes. Unrecognised flags, modes and suffixes remain opaque.
  Recorded EE20 notifications carry percentage brightness. EE30 has an opaque
  prefix followed by independent overall-power and projection-power flags.
  Neither notification confirms settings, speaker state or projector appearance.
seq:
  - id: header
    contents: [0xaa]
  - id: domain
    type: u1
    enum: domain
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'domain::power': projection_info
        'domain::brightness': h600a_status_reply::brightness_body
        'domain::colour_mode': h600a_status_reply::colour_mode_body
        'domain::firmware': h600a_status_reply::version_body
        'domain::hardware': h600a_status_reply::hardware_body
        'domain::pact': pact_info
  - id: checksum
    type: u1
enums:
  domain:
    0x34: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0xef: pact
types:
  brightness_notification:
    seq:
      - id: header
        contents: [0xee, 0x20]
      - id: body
        size: 17
        type: h600a_status_reply::brightness_body
      - id: checksum
        type: u1
    instances:
      domain:
        value: domain::brightness
  power_notification:
    seq:
      - id: header
        contents: [0xee, 0x30]
      - id: body
        type: power_change
      - id: checksum
        type: u1
    instances:
      domain:
        value: domain::power
  power_change:
    seq:
      - id: unknown_prefix
        type: u1
      - id: overall_flags
        type: u1
      - id: projection_flags
        type: u1
      - id: unknown_tail
        size: 14
    instances:
      is_on:
        value: (projection_flags & 0x01) != 0
  pact_info:
    seq:
      - id: pact_type
        type: u2be
      - id: pact_code
        type: u1
      - id: unknown_tail
        size-eos: true
  projection_info:
    seq:
      - id: flags
        type: u1
      - id: brightness
        type: u1
      - id: speaker_status
        type: u1
      - id: sound_code
        type: u1
      - id: volume
        type: u1
      - id: unknown_tail
        size-eos: true
    instances:
      is_on:
        value: (flags & 0x40) != 0
      pairing_prompt:
        value: (flags & 0x08) != 0
      quiet_start:
        value: (flags & 0x20) != 0
      local_sound_enabled:
        value: (flags & 0x04) != 0
      dreamview_laser:
        value: (flags & 0x02) != 0
      sound_playing:
        value: (speaker_status & 0x80) != 0
