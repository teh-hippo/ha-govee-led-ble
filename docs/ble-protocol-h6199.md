# Govee H6199 "DreamView T1" BLE protocol and integration audit

Expected H6199 protocol determined by protocol analysis of the app's BLE traffic, and the concrete
discrepancies against our integration. **We hold no dedicated H6199 captures** (all our captures are
H617A) and must **never direct-drive the H6199** (device policy) — so H6199 fixes are confirmed by
*passively sniffing the app* controlling the TV (compare-mode of `tools/ble/validate_protocol.py`),
not by driving it. The frame layouts below are pending live confirmation on the wire.

## Module and framing

H6199 = goodsType **24** (TV-backlight SKU); 15 segments; sibling SKU H6198.
Frame `[proType][commandType][ext…][XOR@19]`; proType `0x33`
write / `0xAA` read; multi-function commandType `0x05`. Sub-mode byte:
`00`=Video, `04`=Scenes, `0a`=DIY, `0b`=Colour(old), `0c`=Music(old), `13`=MusicV2, `15`=ColourV2.
Old vs new encoders are **firmware-generation gated**.

## Expected frame layouts

The frames the app emits on the wire for each feature (observable by passively sniffing the app):

| Feature | App frame | Notes |
|---|---|---|
| Video mode | `33 05 00 <region> <dynamic> <sat> <sound> <voice> <bri>` (fixed 7-byte body) | fixed 7-byte body including brightness at `byte[8]` |
| Colour | `33 05 15 01 <R G B> <Khi Klo> <wR wG wB> <mL mH>` | V2 colour frame |
| Colour temp | `33 05 15 01 FF FF FF <Khi Klo> <wR wG wB> FF 7F` (Kelvin big-endian at `[7:9]`) | Kelvin big-endian at `[7:9]` |
| Segment brightness | `33 05 15 02 <bri> <mL mH>` (all = `FF 7F`) | mask `FF 7F` = all segments |
| Music V2 | `33 05 13 <mode> <sens> <subvariant> <!auto> <R G B>` | V2 music frame |
| Scenes | `33 05 04 <lo hi>` (2-byte LE) | 2-byte little-endian scene id |
| White balance | `33 A9 05 03 <v1 v2 v3>` (basic) / `33 A9 05 04 <v1..v4>` (advanced) | basic vs advanced calibration |

Video field meanings: `region` **0=full / 1=part**; `dynamic` =
power vs soft (*not* game/movie); `sat` default 50; `sound` on/off; `voice`
default 50; `bri` = whole-strip brightness (firmware-gated). Music mode
codes: 3=Rhythm, 5=Energic, 6=Rolling, else Spectrum; `byte[5]` is
a mode-specific sub-variant (default 1), not a global "calm". Additional TV commands exist that
we do not implement: light direction `0x30`, camera position `0x31`, camera check `0x32`, and an
`0xA9` family (saturation, sensitivity, HDR, auto-WB, AI filter, black-screen/border).

## Discrepancies vs our integration (prioritised)

| Sev | Our code | We send | App sends | Action |
|---|---|---|---|---|
| HIGH | `protocol.py` `build_video_mode` (region) | full → `byte[3]=1` | full → `0` | **Verify live**, then invert polarity + parse |
| HIGH | `build_video_mode` (body) | 4/6-byte body, `byte[8]` omitted → bri 0 | fixed 7-byte incl. `byte[8]` brightness | **Verify live**, then emit full body (bri default 50) |
| HIGH | `build_white_brightness` | `15 02 <pct>` (mask `00 00` = no-op) | `15 02 <pct> FF 7F` | **Safe fix**: append `FF 7F` |
| HIGH | `build_video_white_balance` | `A9 00 03 01 <r b>` (cites an iOS capture) | `A9 05 03 <v1 v2 v3>` | **Conflict — re-capture live** before changing |
| MED | `light.py` video "game/movie" | `byte[4]` = game/movie | `byte[4]` = power/soft dynamic | Relabel after live confirm |
| MED | `const.py` H6199 profile | no scenes/DIY exposed | scenes `04 lo hi`, DIY `0a` | Add scene source or document omission |
| MED | `build_music_mode_with_color` | `byte[5]` = calm(0/1) | `byte[5]` = sub-variant (default 1) | Relabel; default 1; stop gating on rhythm |
| MED | `protocol.py` (encoders) | V2 encoders only | older firmware uses old `0x0c` colour/music encoders | Detect older firmware or document V2+ baseline |
| LOW | video defaults | sat 100 / voice 0 | sat 50 / voice 50 | Align or document |

**Resolved (encoder now matches the app's on-wire frames; H6199 still needs a live confirm):**
`build_color_temp` sends the Kelvin field `byte[7:9]` (shared with H617A); music sensitivity clamps
0-99 (MIN 0 / MAX 99, shared across models); `build_scene` emits a fixed 2-byte LE id.

**Verified correct:** `build_color_rgb`, `build_power`, `build_brightness`, music mode IDs
(energic 5 / rhythm 3 / rolling 6), white-balance command type `0xA9`, `!autoColor` marker `0x01`,
sub-mode constants.

## Needs live H6199 capture to confirm (passive app-sniff only)

- White-balance payload: our `A9 00 03 01 r b` vs app `A9 05 03 v1 v2 v3` — confirm sub-selector,
  value count and order before changing (this is a genuine conflict, not a clear bug).
- Video: `byte[8]` brightness honoured? region polarity? `byte[4]` power/soft?
- Segment mask: `15 02 pct 00 00` truly a no-op vs `… FF 7F` = all segments (also H617A open-q #3).
- Music `byte[5]` sub-variant effect; Spectrum code `0x04`.
- Device firmware generation (old vs new) → decides `0x13` vs `0x0c` music, V2 vs old colour.
- Whether H6199 answers `aa 01/04/05` reads or only `0xA9` video-extended reads.
