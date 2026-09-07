meta:
  id: govee_common
  title: Govee H617A shared BLE wire datatypes (imported by the per-payload specs)
  endian: le
  imports:
    - govee_shared
types:
  a3_header:
    seq:
      - id: marker
        contents: [0x01]
      - id: linecount
        type: u1
        valid:
          min: 2
  diy_selector:
    seq:
      - id: code
        type: u2le
  music_selector:
    seq:
      - id: mode_id
        type: u1
        enum: music_mode
      - id: sensitivity
        type: u1
      - id: style
        type: u1
      - id: manual_color_count
        type: u1
      - id: rgb
        type: govee_shared::rgb
        if: manual_color_count >= 1
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
    # Ids beyond the eleven above. Present so a frame carrying one can be PARSED and BUILT at
    # all; which ids a given device accepts is a profile decision, not a grammar one -- an
    # H66A0 refuses 0x36 and 0x38-0x3b while running everything else here, and an H1A42
    # refuses the whole 0x30-0x3b block while accepting 0x84, 0x85, 0x92 and 0xa3.
    0x36: waves
    # The RGBIC variants of Rhythm and Energic. Both exist twice in the vendor registry.
    0x38: rhythm_rgbic
    0x39: energetic_rgbic
    0x3a: rippling
    0x3b: swiping
    # Swept from a device on 2026-08-27; the registry runs far past 0x3b.
    0x53: flowing_light
    0x54: spectrum_alt
    0x55: color_painting
    0x65: meteor
    0x78: windmill
    0x84: splash
    0x85: spring
    # Swept from an H1A42 strip on 2026-08-27. Neither id has an entry in
    # IMusicEffectStatic.parseSubStr4New, so the names come from SubMusicModeConfig instead:
    # makeLianYi$default defaults to RhyRule.op_type_trigger_finish_clean (146 = 0x92) and its
    # maker labels it R.string.b2light_scenes_ripple; makeYouDong$default defaults to -93
    # (0xa3) and passes R.string.app_move_about. strings.xml renders those "Ripple" and
    # "Orbit". Transcribed, not invented.
    0x92: ripple
    0xa3: orbit
