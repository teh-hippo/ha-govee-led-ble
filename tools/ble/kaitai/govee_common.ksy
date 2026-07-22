meta:
  id: govee_common
  title: Govee H617A shared BLE wire datatypes (imported by the per-payload specs)
  endian: le
doc: |
  Provably-common wire structures shared across the H617A protocol specs, defined
  once here and imported so they cannot drift between payloads. A structure earns a
  place here only if it is multi-field (or a drift-prone enum dataset) AND used by
  two or more specs; single-use structures stay local to their spec, and single
  self-validating fields (such as trailing zero padding, valid: 0) stay inline.
  Captures are ground truth: every importing spec round-trips real bytes that
  exercise these types, so sharing is a claim of proven sameness, not convenience.
  Evidence tags follow the same vocabulary as the payload specs:
  [CONFIRMED_LIVE] / [INFERRED] / [INHERITED].
types:
  rgb:
    doc: |
      One ordered RGB colour triplet, three raw bytes R,G,B on the wire. Proven
      identical across every DIY/scene/workshop/music palette and the aa segment
      read-back, so it is defined once and imported by all of them.
    seq:
      - id: r
        type: u1
        doc: '[CONFIRMED_LIVE] red channel 0-255'
      - id: g
        type: u1
        doc: '[CONFIRMED_LIVE] green channel 0-255'
      - id: b
        type: u1
        doc: '[CONFIRMED_LIVE] blue channel 0-255'
  a3_header:
    doc: |
      The two leading bytes shared by every reassembled 0xA3 multi-frame body:
      01 <linecount>. The A3 payload TYPE byte follows in each payload spec (it is
      payload-specific and disambiguated by the activation frame, so it is not part
      of this shared header). linecount is the 17-byte A3 data-chunk count and is
      never below 0x02; its per-payload values are documented at each use site.
    seq:
      - id: marker
        contents: [0x01]
        doc: '[CONFIRMED_LIVE] raw 0x01 generic build_a3_multi body marker'
      - id: linecount
        type: u1
        valid:
          min: 2
        doc: '[CONFIRMED_LIVE] 17-byte A3 frame count as the sender wrote it; equals reassembled_body_len // 17 in every observed capture. Some senders count an appended empty 0xFF terminator frame, others do not (see per-payload docs). Never observed below 0x02.'
enums:
  music_mode:
    0x05: energetic
    0x03: rhythm
    0x04: spectrum
    0x06: rolling
    0x30: bloom
    0x31: shiny
    0x32: separation
    0x33: hopping
    0x34: piano_keys
    0x35: fountain
    0x37: day_and_night
