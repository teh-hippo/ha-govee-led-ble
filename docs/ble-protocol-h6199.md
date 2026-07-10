# Govee H6199 "DreamView T1" BLE protocol and integration audit

H6199 protocol, **confirmed by passively sniffing the Govee app** driving the TV (live app-sniff
2026-07-10; we never direct-drive the H6199, per device policy). The capture **validated the
integration's H6199 encoders on the wire**: the pre-capture "discrepancies" below were mostly wrong
hypotheses and are now marked resolved. Frame layouts are confirmed unless noted otherwise.

## Module and framing

H6199 = goodsType **24** (TV-backlight SKU); 15 segments; sibling SKU H6198.
Frame `[proType][commandType][ext…][XOR@19]`; proType `0x33`
write / `0xAA` read; multi-function commandType `0x05`. Sub-mode byte:
`00`=Video, `04`=Scenes, `0a`=DIY, `0b`=Colour(old), `0c`=Music(old), `13`=MusicV2, `15`=ColourV2.
Old vs new encoders are firmware-generation gated; the captured device (fw 1.10.04) is **V2**
(all frames were `00`/`13`/`15`/`a9`), so V2 is the correct baseline.

## Frame layouts (confirmed on the wire 2026-07-10)

| Feature | Frame | Notes |
|---|---|---|
| Video mode | `33 05 00 <region> <sub-mode> <sat>` | region **1=full / 0=part**; sub-mode movie(0)/game(1); brightness is NOT in this frame |
| Colour | `33 05 15 01 <R G B> <Khi Klo> <wR wG wB> <mL mH>` | V2 colour frame |
| Colour temp | `33 05 15 01 FF FF FF <Khi Klo> <wR wG wB> FF 7F` | Kelvin big-endian at `[7:9]`; reads back as the white-point RGB (no kelvin) |
| Brightness | `33 04 <pct>` | whole-strip brightness is its own command, not a video-frame byte |
| Segment brightness | `33 05 15 02 <bri> <mL mH>` (all = `FF 7F`) | mask `FF 7F` = all segments |
| Music V2 | `33 05 13 <mode> <sens> <style> <count> <R G B>` | style at `byte[5]`, colour count/auto at `byte[6]` |
| Scenes | `33 05 04 <lo hi>` (2-byte LE) | the H6199 does expose scenes on the wire |
| White balance | `33 A9 00 03 01 <v2 v3>` | selector `00 03`; the app does **not** use `A9 05 03` |

Video field meanings: `region` **1=full / 0=part**; `sub-mode` = movie(0)/game(1) (the app's
DreamView video modes); `sat` default. Whole-strip brightness is a separate `33 04` write, not a
video-frame byte. Music mode codes: 3=Rhythm, 5=Energic, 6=Rolling, 4=Spectrum; `byte[5]` is the
style (for Rhythm: dynamic 0 / calm 1) and `byte[6]` is the colour count (0 = auto-colour). Additional
TV commands exist that we do not implement: light direction `0x30`, camera position `0x31`, camera
check `0x32`, and an `0xA9` family (saturation, sensitivity, HDR, auto-WB, AI filter,
black-screen/border).

## Integration audit vs the 2026-07-10 capture

The pre-capture audit predicted several HIGH-severity discrepancies. The live capture **disproved
them**: the integration's encoders match the app. Do **not** "fix" these against an older hypothesis.

| Prior claim (pre-capture) | Capture result | Status |
|---|---|---|
| `build_video_mode` region polarity inverted (full should be `0`) | app sends full=`1`, part=`0` — same as our code | RESOLVED: our code correct |
| `build_video_mode` must emit a 7-byte body incl. `byte[8]` brightness | video frame carries no brightness; brightness is a separate `33 04` write | RESOLVED: our code correct |
| `build_video_white_balance` should be `A9 05 03` (conflict) | app sends `A9 00 03 01 <v2 v3>` — matches our `A9 00 03` | RESOLVED: our code correct |
| `build_music_mode_with_color` `byte[5]` mislabelled | `byte[5]` = style, `byte[6]` = colour count/auto — matches our encoder | RESOLVED: our code correct |
| H6199 exposes no scenes | scenes `33 05 04 <lo hi>` seen on the wire | scenes exist (effect surface can add them later) |
| Older firmware uses `0x0c` colour/music | captured device is V2 (`0x13`/`0x15`) | V2 baseline confirmed for fw 1.10.04 |

**Verified correct (unchanged):** `build_color_rgb`, `build_power`, `build_brightness`,
`build_color_temp` (shared Kelvin field), `build_scene` (2-byte LE id), music mode IDs
(energic 5 / rhythm 3 / rolling 6 / spectrum 4), white-balance command type `0xA9`, `!autoColor`
marker `0x01`, sub-mode constants. The H6199 answers `aa 01/04/05` reads (confirmed 2026-07-10).

## Remaining (low priority, not blocking)

- `byte[4]` movie/game is exposed as the two DreamView sub-modes; a final on-TV visual confirm of the
  game sub-mode is a nice-to-have, not a blocker (both values engage video and were seen on the wire).
- Older (pre-V2) H6199 firmware `0x0c` colour/music encoders remain unimplemented (out of scope; the
  supported devices are V2).
