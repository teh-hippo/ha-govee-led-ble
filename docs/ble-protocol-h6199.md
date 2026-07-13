# Govee H6199 "DreamView T1" BLE protocol and integration audit

H6199 protocol, **confirmed by passively sniffing the Govee app** driving the TV (live app-sniffs
2026-07-10 and 2026-07-12; we never direct-drive the H6199, per device policy). Frame layouts and
field meanings below distinguish byte-confirmed behaviour from controls whose UI mapping remains
unproven.

## Module and framing

H6199 = goodsType **24** (TV-backlight SKU); 15 segments; sibling SKU H6198.
Frame `[proType][commandType][ext…][XOR@19]`; proType `0x33`
write / `0xAA` read; multi-function commandType `0x05`. Sub-mode byte:
`00`=Video, `04`=Scenes, `0a`=DIY, `0b`=Colour(old), `0c`=Music(old), `13`=MusicV2, `15`=ColourV2.
Old vs new encoders are firmware-generation gated; the captured device (fw 1.10.04) is **V2**
(all frames were `00`/`13`/`15`/`a9`), so V2 is the correct baseline.

## Frame layouts (confirmed on the wire through 2026-07-12)

| Feature | Frame | Notes |
|---|---|---|
| Video mode | `33 05 00 <region> <sub-mode> <sat> <sound> <softness> 00` | region **1=All / 0=Part**; sub-mode movie(0)/game(1); sound 0/1, softness 1-100; brightness is NOT in this frame |
| Colour | `33 05 15 01 <R G B> <Khi Klo> <wR wG wB> <mL mH>` | V2 colour frame |
| Colour temp | `33 05 15 01 FF FF FF <Khi Klo> <wR wG wB> FF 7F` | Kelvin big-endian at `[7:9]`; reads back as the white-point RGB (no kelvin) |
| Brightness | `33 04 <pct>` | whole-strip brightness is its own command, not a video-frame byte |
| Segment brightness | `33 05 15 02 <bri> <mL mH>` | H617A-derived shape; no H6199 segment write is attributable, so this remains gated |
| Music V2 | `33 05 13 <mode> <sens> [...]` | the four current modes are proven with mode+sensitivity only; style/count/RGB remain unconfirmed on H6199 |
| Scenes | `33 05 04 <lo hi> <type>` | type `01` for captured simple activation; type `02` after a type-`02` A3 body |
| White balance | `33 A9 00 03 01 <red> <blue>` | raw components vary independently; the app-control mapping is unproven and is not surfaced |
| Blank screen | `33 A9 0A 06 <enabled> 02 0A 00 78 00` | enable 0/1 and the 2-minute value are attributable; inner mode fields remain unproven |

Video field meanings: `region` **1=All / 0=Part**; `sub-mode` = movie(0)/game(1) (the app's
DreamView video modes); `sat` default. Whole-strip brightness is a separate `33 04` write, not a
video-frame byte. Music mode codes: 3=Rhythm, 5=Energetic, 6=Rolling, 4=Spectrum. Sound Off/On/Off
and softness full/min/full were revert-checked in the current app. The app always sent the full
video frame and retained softness while sound was off. No `aa 05` video-mode reply was captured,
so video read-back offsets remain unproven. Additional
TV commands exist that we do not implement: light direction `0x30`, camera position `0x31`, camera
check `0x32`, and an `0xA9` family (sensitivity, HDR, auto-WB, AI filter and
black-screen/border).

## Integration audit vs the 2026-07-10 capture

The pre-capture audit predicted several HIGH-severity discrepancies. The live capture **disproved
them**: the integration's encoders match the app. Do **not** "fix" these against an older hypothesis.

| Prior claim (pre-capture) | Capture result | Status |
|---|---|---|
| `build_video_mode` region polarity inverted (full should be `0`) | app sends full=`1`, part=`0` — same as our code | RESOLVED: our code correct |
| `build_video_mode` must emit a 7-byte body incl. `byte[8]` brightness | video frame carries no brightness; brightness is a separate `33 04` write | RESOLVED: our code correct |
| `build_video_white_balance` should be `A9 05 03` (conflict) | app sends `A9 00 03 01 <red blue>` | selector resolved; the old one-dimensional interpolation was disproven |
| `build_music_mode_with_color` extended fields apply to H6199 | current H6199 capture exercised mode+sensitivity only | extended style/count/RGB fields remain model-unconfirmed |
| H6199 exposes no scenes | scenes `33 05 04 <lo hi> <type>` seen on the wire | scenes exist (effect surface can add them later) |
| Older firmware uses `0x0c` colour/music | captured device is V2 (`0x13`/`0x15`) | V2 baseline confirmed for fw 1.10.04 |

**Verified correct:** `build_color_rgb`, `build_power`, `build_brightness`,
`build_color_temp` (shared Kelvin field), the four music mode IDs, white-balance command type
`0xA9`, sub-mode constants, the video sound/softness extension and `build_h6199_scene`. H6199 scene
activation carries its captured third type byte and is not the H617A two-byte builder. H6199
answered the current identity handshake; hardware query is `aa 07 03` and returned `3.02.01`.

## Integration safety gating

The integration exposes only the H6199 behaviours validated for the captured firmware:

- base colour, brightness and colour temperature;
- movie/game video, capture region and saturation;
- video sound effects and softness;
- Energetic, Rhythm, Spectrum and Rolling music modes;

H6199 DIY is now confirmed to exist, but it uses a distinct activation path (`0x61` for captured
Fade1), so H617A-derived animated DIY encoders remain rejected until the H6199 grammar is mapped.
Static segment writes, white-balance UI control, extended music modes, timers and power-off memory
remain gated. Existing
unsupported saved effects remain exportable but cannot be applied.

## Remaining

- Map white balance through known app-control positions; the two raw bytes are independent.
- Capture an `aa 05` reply in video mode to prove read-back semantics.
- Attribute a non-Fade DIY family/variant and a speed A/B/A before enabling H6199 authoring.
- Attribute any H6199 segment write before exposing segment services or static custom effects.
- Confirm whether music style/colour fields exist on H6199 rather than inheriting H617A semantics.
- Decode Blank Screen inner fields and per-side relative brightness.
- Older (pre-V2) H6199 firmware `0x0c` colour/music encoders remain unimplemented (out of scope; the
  supported devices are V2).
