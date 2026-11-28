meta:
  id: h60b0_effect_upload
  title: H60B0 candidate A3 effect envelope
  imports:
    - ../govee_common
    - h60b0_music_body
doc: |
  SPECULATIVE: Exact-model upload routing.
  The envelope retains all content and transport fill. Native DIY content
  requires separately qualified revision context; a converted combined body
  is not a canonical scene body. The preferred combined scene route is 5a;
  hardware also accepted the 0a route with the 51/length wrapper and nested
  0a removed from the body.
  The music selector echo is the outer mode. Scene acceptance was observed
  visually over LAN and is not byte-capture evidence for BLE.
seq:
  - id: header
    type: govee_common::a3_header
  - id: kind
    type: u1
    enum: kind
  - id: mode
    type: u1
    enum: h60b0_music_body::music_mode
    if: kind == kind::music
  - id: content
    size-eos: true
enums:
  kind:
    0x0a: rgbic_scene
    0x41: music
    0x58: native_diy
    0x5a: combined_scene
