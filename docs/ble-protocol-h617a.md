# Govee H617A BLE protocol reference

A protocol reference for local Bluetooth LE control of the Govee H617A RGBIC LED strip. It is
derived from live captures of the vendor iOS app, decoded with `tools/ble/decode_govee.py`, and
approved direct validation against the designated test strip. Confirmed commands are cross-checked
against the current builders in `custom_components/ha_govee_led_ble/protocol.py` and `scenes.py`.

Companion documents:

- Effect content (scene catalogue, DIY families, parameters, capture plan):
  [`ble-effect-catalogue.md`](ble-effect-catalogue.md).
- Capture and decode method: [`ble-capture-workflow.md`](ble-capture-workflow.md).
- H6199 model-specific protocol: [`ble-protocol-h6199.md`](ble-protocol-h6199.md).
- Current verification backlog: [`ble-protocol-open-questions.md`](ble-protocol-open-questions.md).

Status: power, brightness, RGB and white/Kelvin colour, per-segment control, scenes, all 11 music
modes and scheduled timers are implemented and confirmed live on firmware `3.02.24`. Flat, Finger
Sketch, Vibrant, and Combo builders exist; Flat and Vibrant remain experimental,
while Finger Sketch and Combo are directly validated. rgbicv2 effects can replay captured bodies through
`build_scene_multi`, and Workshop authoring remains fail-closed where packed value spaces are not
proven. See section 7 for implementation status. Raw pcaps remain outside the repository because
they contain live BLE traffic.

## 1. Overview and device

- Model: H617A. Hardware `3.01.01`, firmware `3.02.24`.
- 15 addressable segments, reported by the strip as 5 groups of 3 segments.
- The integration also supports the H6199, which uses model-specific DreamView, scene, DIY, and
  capability rules. See [`ble-protocol-h6199.md`](ble-protocol-h6199.md).

### Model identification

The captured device is an H617A, confirmed by several independent signals:

- The captured "Halloween" scene used code `1173`, which is H617A's code. H619A and H6199 use
  `2497` for the same scene.
- Home Assistant advertises the strip as `Govee_H617A_*`.
- The packaged `scenes.py` catalogue matches the live H617A catalogue.

H619A and H6199 use different scene codes for most scenes (for example Halloween `2497` vs
`1173`, Forest `212` vs `2163`) and would need their own catalogue. The per-model scene lists
are in [`ble-effect-catalogue.md`](ble-effect-catalogue.md).

## 2. Transport and framing

- GATT write: handle `0x0014`, UUID `00010203-0405-0607-0809-0a0b0c0d2b11` (`WRITE_UUID`).
- GATT notify: handle `0x0010`, UUID `...2b10` (`READ_UUID`).
- Every frame is 20 bytes and `byte[19] = XOR(byte[0..18])`. Payloads shorter than 19 bytes
  are zero-padded before the checksum is appended.
- Frame headers (`byte[0]`):
  - `0x33` command (phone to strip).
  - `0xAA` query (phone to strip) and reply (strip to phone).
  - `0xA3` multi-frame upload (phone to strip), used for scenes, DIY and Vibrant.

Byte offsets in this document are half-open ranges, so `[12:14]` means `byte[12]` and
`byte[13]`.

### Connect handshake and keep-alive

On connect the app performs an initial-state handshake, then settles into a keep-alive poll.
Confirmed app requests are:

1. Identity and capability queries, each sent once: `aa 07 03` hardware version, `aa 06` firmware
   version, `aa 04` brightness, `aa 40` segment count, `aa 05` colour mode, `aa 23 ff` timer table,
   `aa 11` sleep timer, `aa 12` wake-up timer.
2. Steady state: the app polls `aa 01` (power) roughly every 2 seconds as a keep-alive; the strip
   replies `aa 01 01` when on.

The device also emits per-segment state replies `aa a5 <group>` for groups 1..5 during startup.
The exact app request has not been isolated and must not be inferred from the reply selector.

The app may also send a clock sync `33 09 <7-byte time>` (informational, seen in earlier captures;
not required to control the strip). The handshake replies establish the device identity (firmware
`3.02.24`, hardware `3.01.01`, 15 segments) and the current mode/state before any control command
is sent.

## 3. Command reference (0x33)

Every control command uses header `0x33`. `byte[1]` selects the function; the colour family
(`byte[1] = 0x05`) is further multiplexed by `byte[2]`. All frames are padded to 19 bytes with
a trailing XOR checksum (omitted from the table for brevity). `<..>` marks a variable byte.

| Function | Frame | Notes |
|---|---|---|
| Power | `33 01 <on>` | `on`: `01` = on, `00` = off. |
| Whole-strip brightness | `33 04 <pct>` | Master brightness, `pct` 0-100. |
| Colour (whole or per-segment) | `33 05 15 01 <R> <G> <B> 00 00 00 00 00 <ML> <MH>` | 16-bit little-endian segment mask at `[12:14]`; all segments = `0x7FFF`. |
| Colour temperature | `33 05 15 01 00 00 00 <Khi> <Klo> <R> <G> <B> <ML> <MH>` | RGB slot `[4:7]` is zero; Kelvin is 16-bit big-endian at `[7:9]`; Govee's rendered white RGB at `[9:12]`. |
| Per-segment brightness | `33 05 15 02 <pct> <ML> <MH>` | Segment mask at `[5:7]`, immediately after the percent. Independent of colour. |
| Scene select | `33 05 04 <code_LE>` | Scene code, little-endian; preceded by `0xA3` frames for complex scenes. |
| DIY select (flat / Finger Sketch / Combo) | `33 05 0a <slot> [type]` | Mode `0x0a`; preceded by the `0xA3` DIY body (`TYPE 0x04`, `0x03`, or `0x04` with `FAMILY 0xFF`). Finger Sketch appends its `TYPE 0x03` after the slot and uses a fixed slot `0x20` (`33 05 0a 20 03`, live-confirmed). Combo/Flat omit the trailing type; slot is app-assigned and persistent per saved effect (current Combo examples used `0x6E` and `0xEF`). The integration's default `0xF0` was accepted and read back, but app captures also used `0xF0`, so it does not prove ownership. |
| rgbicv2 DIY select | `33 05 04 <code_LE>` | Rich DIY effects reuse the scene command with a per-effect code (Bloom 506, Brilliant 501, ...); preceded by the `0xA3` record-container body (`TYPE 0x02`). |
| Workshop Apply | `33 05 04 91 01 02` | Workshop code `0x0191`, little-endian, with scene type `0x02`; preceded by the length-delimited Workshop `0xA3` body (`TYPE 0x02`). |
| Vibrant activate | `33 05 0a <slot>` | Same activation as DIY; preceded by the `0xA3` Vibrant body (type `0x03`). |
| Music mode | `33 05 13 <mode> <sens> <style> <count> <RGB×count>` | H617A uses sub-command `0x13` (an older protocol version emits `0x0c`); see "Music mode layout". All 11 `mode` codes confirmed live (match `const.MUSIC_MODES`); `sens` 0-99; `style` `00` Dynamic / `01` Calm; `count` = manual colour count and the auto-colour flag (`00` = Auto colour on). Extended modes also send a `0x41` `a3` parameter frame. |
| Video mode (H6199) | `33 05 00 <region> <game> <sat> <sound> <softness>` | Current H6199 app frame. Sound and softness are always present; see the H6199 reference. |
| Video white balance (H6199) | `33 a9 00 03 01 <red> <blue>` | Raw independent DreamView components; app-control mapping is not yet surfaced. |
| Timer / schedule | `33 23 <idx> <enableAndType> <hour> <min> <repeat>` | 4 on/off slots. Related: sleep `33 11`, wake-up `33 12`, gradual `33 14`. See "Timer subsystem". |
| Clock sync (handshake) | `33 09 <7-byte time>` | Sent on connect; informational. |

The music-mode command is confirmed on the H617A (see "Music mode layout"). Video mode is **not**
offered for the H617A in the app, so `33 05 00` and `33 a9` are H6199-only commands.

### Colour frame layout

The static colour command shares one 20-byte frame between whole-strip and per-segment
colour. Only the segment mask changes.

```
offset: 0  1  2  3   4  5  6  7  8  9 10 11 12 13 .. 19
byte:   33 05 15 01  RR GG BB 00 00 00 00 00 ML MH .. XOR
                     \_ RGB _/                 \mask/
```

- `ML MH` is a 16-bit little-endian bitmask, bit `N` = segment `N` (0..14). All 15 segments =
  `0x7FFF` (`ff 7f`).
- Verified end-to-end: with the app closed, sending segments 0-6 red (mask `0x007F`) and
  segments 7-14 green (mask `0x7F80`) produced exactly that split, and reading the state back
  matched.

### Colour temperature layout

White or temperature mode reuses the `15 01` sub-command but zeroes the RGB slot and carries
the Kelvin value plus Govee's own white rendering.

```
offset: 0  1  2  3   4  5  6   7   8   9 10 11 12 13 .. 19
byte:   33 05 15 01  00 00 00 Khi Klo RR GG BB ML MH .. XOR
                     \RGB = 0/ \Kelvin/ \white/  \mask/
```

- Kelvin is a 16-bit big-endian value at `[7:9]` (for example 3000 K = `0b b8`).
- The white RGB at `[9:12]` is a rendered preview of the temperature, not colour-critical. The
  samples below are the vendor app's rendering, measured on the wire; `build_color_temp` computes
  its own preview via `kelvin_to_rgb`, which can differ by a few counts. Only the Kelvin field is
  validated byte-for-byte, so the preview bytes are not byte-compared.

  | Kelvin | App white RGB (measured) | Hex |
  |---|---|---|
  | 2000 | (255, 141, 11) | `FF8D0B` |
  | 3000 | (255, 185, 105) | `FFB969` |
  | 4300 | (255, 219, 175) | `FFDBAF` |
  | 5300 | (255, 235, 215) | `FFEBD7` |
  | 9000 | (217, 225, 255) | `D9E1FF` |

`build_color_temp` emits exactly this frame (Kelvin at `[7:9]`, RGB slot zeroed); confirmed live
over 2000-9000K.

> Reconfirmed by the current-iOS Color walkthrough (2026-07-16). The Color tab exposes three
> sub-tabs: **Whole** (solid RGB via Basic Colors and a Color Wheel, plus the Color temperature
> slider), **Subsection** (per-segment colour with a serpentine 15-node selector, Select all /
> Deselect all / Invert, and a Relative brightness slider), and **Vibrant** (the static gradient
> bar). Whole colour sent `33 05 15 01 <rgb> ... FF 7F` (red/blue/white/wheel all exact); the white
> Basic swatch is RGB `FF FF FF`, distinct from the Kelvin temperature frame. Colour temperature
> endpoints matched the table above exactly (warm 2000 K `FF8D0B`, cool 9000 K `D9E1FF`).
> Selecting segment 1 alone sent colour mask `0x0001` and a relative-brightness change sent
> `33 05 15 02 <pct> 01 00`, confirming the per-segment mask. No mismatches.

### Per-segment brightness layout

```
offset: 0  1  2  3   4  5  6 .. 19
byte:   33 05 15 02  PP ML MH .. XOR
                     |  \mask/
                     percent
```

- The mask sits at `[5:7]`, not `[12:14]` as in the colour frame.
- Verified: `33 05 15 02 11 7f 00` = 17% on mask `0x007F` (segments 0-6); `33 05 15 02 01 00 40`
  = 1% on segment 14 only. The app sends only the segments that changed.

### Music mode layout

The app's Music tab (distinct from the DIY Music family in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md)) sends a **mode-set frame** and, for the
extended modes, an accompanying **multi-packet colour frame**. Both frames were confirmed by live
capture against the device.

Mode-set frame:

```
offset: 0  1  2    3     4     5      6      7..
byte:   33 05 SUB  MODE  SENS  STYLE  COUNT  <RGB × COUNT>
```

- `SUB` = music sub-command. The H617A uses `0x13` on the wire (confirmed live across all 11
  modes); an older protocol version emits `0x0c`, with an otherwise identical
  payload. The builder ships `0x13`.
- `SENS` = sensitivity, 0-99 (default 99). Confirmed linear on-wire (0/48/99 at min/mid/max).
- `MODE`. All 11 codes are **confirmed live** (H617A, firmware 3.02.24, 2026-07-09) and match
  `const.MUSIC_MODES`:

  | Mode | Code |
  |---|---|
  | Energetic | `0x05` |
  | Rhythm | `0x03` |
  | Spectrum | `0x04` |
  | Rolling | `0x06` |
  | Bloom | `0x30` |
  | Shiny | `0x31` |
  | Separation | `0x32` |
  | Hopping | `0x33` |
  | Piano Keys | `0x34` |
  | Fountain | `0x35` |
  | Day and Night | `0x37` |

  The authoritative captured mapping is `{0x05, 0x03, 0x04, 0x06}`.
- `STYLE` (byte 5): Dynamic (`0x00`) / Calm (`0x01`). Byte-confirmed live for Rhythm, Bloom and
  Shiny; the other modes hold `0x00`. The
  `parse_color_mode_response` decoder currently reports Calm for Rhythm only.
- `COUNT` (byte 6) = manual colour count, and is also the **auto-colour flag**: `0x00` = Auto
  colour on (no RGB follows); `N` = Auto colour off with `N` colours, each a 3-byte RGB. Confirmed
  live on Spectrum: turning Auto colour off set `COUNT 0->1` and appended one RGB triple (byte 5
  STYLE stayed `0x00`), and changing that colour moved only the RGB bytes at `[7:10]`. (This
  corrects an earlier hypothesis that Spectrum/Rolling encoded auto-colour in byte 5.)

Per-mode controls differ: movement modes expose segment/point count
(1..8, clamped by strip length), speed (1..100), direction,
gradient and relative brightness; simple modes expose only the Dynamic/Calm
toggle and auto-colour + one colour. Extended modes ALSO send a colour/parameter frame
(command `0x41`), fragmented over `a3` packets. The reassembled body is
`01 <fragCount> 41 <MODE> <nColours> <RGB×n> <mode-specific tail>`, and the per-mode parameters live
at fixed offsets in that assembled body (offset = concatenated fragment payloads).

**Per-mode `a3` parameter offsets (confirmed live by A/B/A diff with revert):**

| Mode | Parameter | Body offset | Values |
|---|---|---|---|
| Bloom `0x30` | Dynamic/Calm companion | `[27]` | Dynamic=`0x50`; Calm=`0x14` |
| Shiny `0x31` | Dynamic/Calm companion | `[20,21]` | Dynamic=`05,64`; Calm=`14,46` |
| Separation `0x32` | Separation point | `[20]` | `0x01`..`0x05` (5 positions) |
| Separation `0x32` | Gradient | `[21]` | `0x00` off / `0x01` on |
| Hopping `0x33` | Relative brightness | `[29]` | `0x00`..`0x32` (0-50%) |
| Piano Keys `0x34` | Key count | `[27]` | `0x08`..`0x0f` (8-15) |
| Fountain `0x35` | Direction | `[26,28]` | Clockwise=`00,05`; Counterclockwise=`02,05`; Two-way=`01,03` |
| Day and Night `0x37` | Segment count | `[26]` | `0x01`..`0x07` (1-7) |
| Day and Night `0x37` | Speed | `[27]` | `0x01`..`0x32` |

Multi-colour palettes (Separation, Hopping background, etc.) are the `<RGB×n>` groups in the body.
Fountain direction uses the pair `[26,28]`, confirmed across current Clockwise/Two-way/Clockwise
and retained Clockwise/Counterclockwise/Clockwise captures. Rhythm/Spectrum parameters ride the
`33 05 13` frame itself (STYLE byte 5, auto-colour/COUNT byte 6, RGB from byte 7), not the `a3` body.

Verified frames (captured, sub-command `0x13`): `13 05 63 00 01 ff0000` (mode `0x05`, sens 99, one
colour red), `13 03 63 00 00` (mode `0x03`, Auto color on), `13 03 63 01 01 0000ff` (Calm, one
colour blue). Full byte-level detail and per-mode payload tails are kept in internal analysis
notes.

The current iOS Music walkthrough on 2026-07-16 reconfirmed the complete editor surface and its
write boundary. Rhythm writes immediately for sensitivity (`0x00`..`0x63`), Dynamic/Calm,
auto/manual colour and RGB selection. Extended editors stage their parameters until **Apply**,
then send the `0x41` A3 body followed by the base `33 05 13` activation. Representative current
captures reconfirmed Separation point/gradient, Hopping relative brightness, Piano key count,
Fountain direction, Day and Night segment count, and Bloom style. Shiny A/B/A corrected its
companion mapping to Dynamic=`05 64`, Calm=`14 46`. The **From mobile phone** path is a separate
microphone-permission workflow and was left out of BLE mapping at the owner's request.

## 4. Query and status reference (0xAA)

The phone writes `aa <type> 00...` to query; the strip replies `aa <type> <data>` as a
notification. Reply data below is an example unless stated otherwise.

| Type | Meaning | Reply (example) |
|---|---|---|
| `01` | Power | `01` = on. Polled ~2 s as keep-alive. |
| `04` | Brightness | `0x64` = 100%. Mirrors the `33 04` command (`BRIGHTNESS_QUERY`). |
| `05` | Colour mode | First reply byte is the mode: `15 01` = static RGB, `04 <code>` = scene, `00 ..` = video, `13 ..` = music. |
| `06` | Firmware version | `"3.02.24"` (ASCII) |
| `07` | Hardware version | selector `03`, then `"3.01.01"` (ASCII) |
| `11` | Sleep timer (fade-off) | `[enable, startBri, closeMin, curMin]`, e.g. `00 1e 0f 0f` = disabled, start bri 30, close in 15 min. Write command `0x11`. |
| `12` | Wake-up timer (sunrise) | `[enable, endBri, hour, min, repeat, rampMin]`, e.g. `00 64 11 00 00 1e` = disabled, end bri 100, 17:00, every day (`repeat 00`), ramp 30 min. Write command `0x12`. |
| `14` | Gradual on/off | Single state byte; no reply seen when unset. Write command `0x14`. |
| `23` | Timer table (4 on/off slots) | `ff <slot0..3 × 4B>`, each slot `[enableAndType, hour, min, repeat]`. e.g. `ff 01 06 00 80 …`. Write command `0x23`. **Not** segment config. |
| `40` | Segment count | `0f` (15) |
| `a3` | Multi-frame control | - |
| `a5 <group>` | Segment colour and brightness reply | `aa a5 <group>` then 3 segments of `<brightness> <R> <G> <B>`. The request frame is not yet byte-pinned. |

### Segment state readback (`aa a5`)

Replies were observed for groups `01..05`; each carries three segments of four bytes,
`<brightness> <R> <G> <B>`. Group `G` holds segments `3*(G-1)` to `3*(G-1)+2`, so group 1 contains
segments 0 to 2 and group 5 contains segments 12 to 14. For example, a segment set to
full-brightness red reads back as `64 ff 00 00`.

This path confirmed the 5 by 3 grouping and that per-segment brightness is stored independently of
colour. A colour write left each segment's earlier brightness unchanged. The app TX request that
elicits each reply remains an explicit capture gap.

### Timer subsystem (`0x11`/`0x12`/`0x14`/`0x23`)

The timer subsystem is four separate BLE commands, not segment configuration: sleep (`0x11`),
wake-up (`0x12`), gradual (`0x14`) and the 4-slot timer table (`0x23`). The layouts and bit fields
below were confirmed by live capture.

**Scheduled on/off timers (`0x23`), 4 slots.** Write one slot:

```
33 23 <idx> <enableAndType> <hour> <min> <repeat>
      |     |                |      |     |
      |     |                |      |     days bitmask (0x80 = one-time / no repeat, 0x00 = every day)
      |     |                |      minute
      |     |                hour
      |     enableAndType: bit7 (0x80) = enabled, bit0 (0x01) = action (1 on / 0 off). 0x81 = enabled+on.
      slot index 0-3
```

Query `aa 23` returns the whole table: `ff` then four 4-byte slots `[enableAndType, hour, min,
repeat]`. Captured `33 23 00 81 06 00 80` = slot 0, enabled+on, 06:00, no repeat. The `repeat`
byte is `0x80 | weekday-mask` (Mon=bit0 .. Sun=bit6) with two special values. Confirmed live
2026-07-16: one-time = `0x80`, Monday-only = `0x81`, Sunday-only = `0xC0`, and **every day = `0x00`**
(the app never emits `0x7f`/`0xff`; a set high bit marks a one-time or specific-weekday schedule).

**Sleep timer (`0x11`)**: fade the light off, `[enable, startBri, closeMin, curMin]`. Confirmed
live 2026-07-16: enable `33 11 01 32 10 00` (startBri 50, close in 16 min), disable `33 11 00 …`;
read-back `aa 11 00 32 10 00`. The countdown arms the moment the timer is enabled.
**Wake-up timer (`0x12`)**: sunrise alarm, `[enable, endBri, hour, min, repeat, rampMin]` (hour
clamped 0-23, min 0-59). Confirmed live 2026-07-16: every-day `33 12 01 64 11 01 00 1d` (endBri 100,
17:01, ramp 29 min), Monday-only `33 12 01 64 11 01 81 1d`; the `repeat` byte shares the `0x23`
encoding (every day = `0x00`). **Gradual (`0x14`)**: a soft on/off transition toggle, single state
byte; not exposed on the H617A app.

## 5. Colour models

The strip exposes four related but distinct colour behaviours; keeping them separate matters
when wiring entities.

1. Whole-strip colour: the `33 05 15 01` frame with mask `0x7FFF`. `build_color_rgb` hardcodes
   this mask.
2. Per-segment colour: the same frame with a mask selecting specific segments, one frame per
   colour group. Different colours on different segments require multiple frames. A `15 01`
   write does not reset per-segment brightness.
3. Brightness has two independent levels: a whole-strip master brightness (`33 04`) and
   per-segment brightness (`33 05 15 02` with a mask). They are orthogonal to colour and to
   each other.
4. Colour temperature: the white mode in section 3, carrying a real Kelvin value and Govee's
   rendered white RGB. This is distinct from approximating white via a plain RGB frame.

A fifth colour presentation, the Vibrant gradient, is a static per-segment gradient uploaded
over `0xA3`; see section 6.

## 6. Multi-frame (0xA3) body formats

Scenes, DIY effects and Vibrant all upload a definition as a sequence of `0xA3` frames, then
activate it with a short `0x33` command. They share the same framing:

- Each frame is `a3 <idx> <17-byte chunk>` with the XOR checksum at `byte[19]`. `idx` counts
  `00, 01, ...`. Scenes and DIY mark the last data chunk `idx = 0xff`, so `linecount` is the
  number of data chunks; Finger Sketch instead appends a separate empty `idx = 0xff` terminator
  frame, making its `linecount` the data-chunk count plus one. Partial and empty chunks are
  zero-padded to 17 bytes.
- The reassembled body across all chunks begins `01 <linecount> <TYPE> ...`, where `linecount`
  is the chunk count as above (`ceil(payload / 17)` for the scene/DIY form).

DIY uses **four** encodings (content catalogue in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md) section 2). `TYPE` alone is not unique
(rgbicv2 DIY shares `0x02` with scenes, and Vibrant shares `0x03` with Finger Sketch), so the
payload is identified by the `TYPE` and activation pair:

| Payload | `TYPE` | Activation |
|---|---|---|
| Scene | `sceneType` (`0x02`, or `0x01` for a few such as Halloween and Sweet) | `33 05 04 <code_LE>` |
| Flat DIY | `0x04` | `33 05 0a <slot>` |
| Combo DIY | `0x04` (`FAMILY = 0xFF`) | `33 05 0a <slot>` |
| Workshop | `0x02` | `33 05 04 91 01 02` |
| rgbicv2 DIY | `0x02` | `33 05 04 <code_LE>` |
| Finger Sketch DIY | `0x03` | `33 05 0a <slot>` |
| Vibrant | `0x03` | `33 05 0a <slot>` |

Body layouts after `01 <linecount> <TYPE>`:

### Scene

The Govee-authored palette or definition from the API `scenceParam` blob. Activation
`33 05 04 <code_LE>`. The app's per-scene edit pencil (Speed slider + Color Change palette)
re-uploads a modified body through the same path — there is no separate parameter command. Full
detail, including the live-confirmed speed/palette grammar, in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md) section 4.

### Flat DIY (`TYPE 0x04`)

```
FAMILY VARIANT SPEED PLEN <palette RGB...>
```

`FAMILY` is the animation family (equal to the app's internal effect-family code); `VARIANT` is a
family-specific selector with no global formula; `SPEED` is 0-100 (default `0x32` = 50, and the
Music family reuses this slot for Sensitivity); `PLEN` is the palette length in bytes
(colours x 3); `palette` is ordered RGB triplets. Activation `33 05 0a <slot>` with an
app-assigned slot (for example `0xF0`). The confirmed `(FAMILY, VARIANT)` map for every flat
effect is in [`ble-effect-catalogue.md`](ble-effect-catalogue.md) section 2.6.

### Combo DIY (`TYPE 0x04`, `FAMILY 0xFF`)

```
FF <var> <speed> <plen> <palette...> <seqlen> <(FAMILY, VARIANT) pairs>
```

Chains one to four compatible flat effects behind one shared palette and speed.
`seqlen = 2 x effect_count`, and each pair reuses the flat `(FAMILY, VARIANT)` values.
Confirmed Fade1 + Marquee1:
`... 15 <7 colours> 04 00 00 03 03 00` (`seqlen 0x04`, pairs `(00,00)` and `(03,03)`, trailing
pad). Activation is `33 05 0a <slot>`.

Current iOS 7.5.21 evidence confirms:

- one to four steps, sequence lengths `0x02`, `0x04`, `0x06`, `0x08`;
- duplicate steps, with remove and re-add as the only ordering operation;
- one shared palette of one to eight colours;
- shared speed `0x00..0x64`, with new-Combo default `0x33`;
- fixed body variant `0x00`, with no corresponding editor control;
- exactly Fade1-3, Jumping1-2, Twinkle1-3, Marquee1-3, Chasing1-2 and Rainbow1-2 in the
  Combo picker; Flat Music1-3 and Crossing are excluded;
- immediate body upload plus activation after every edit; Apply only re-sends the same
  transaction, while Save and other library metadata changes send no Govee BLE command;
- app-assigned slot `0x6E` in one editor and `0xEF` in a separate editor. Slot `0xEF` persisted
  after Save and reopen, proving that the activation byte is an effect handle rather than a
  body-derived value;
- default integration slot `0xF0` directly accepted on H617A firmware 3.02.24. The probe sent the
  exact Combo body, activated `33 05 0a f0`, and received fresh colour-mode read-back
  `aa 05 0a f0`. Legacy app captures also used `0xF0`, so read-back confirms only the slot, not
  which body or author is active.

### Workshop (`TYPE 0x02`, code `0x0191`)

Workshop is a separate length-delimited layer container. Apply sends the body with A3 type `0x02`,
then activates it with `33 05 04 91 01 02`. The strip acknowledges the A3 chunk count and the
colour command. Save was kept separate and was not required for transport.

The semantic body is:

```
<layer_count> [<record_len=1d> <29-byte layer record>]...
```

A copied second layer increments `layer_count` and appends another complete record. Any zeroes
needed to fill the final 17-byte A3 chunk are transport padding outside the length-delimited
records.

The first valid current-iOS anchor used one **Select IC Continuously** layer with ordered red and
blue colours:

```
01 1d 00 01 00 0f 10 01 ff0000 80 14 14 01 80 14 02 ff0000 0000ff 00 00 80 00 00 80 00
```

An untouched draft and a one-red-colour draft emitted no Workshop write. Red plus blue emitted the
body above, establishing two colours as the minimum observed valid colour content.

The Select Type wire enum and its two record parameters are directly mapped:

| Current iOS label | Wire value | Parameters | Current default meaning |
|---|---:|---|---|
| Segment | `00` | `00 07` | Seven segments |
| Select IC Continuously | `01` | `00 0f` | Fifteen ICs |
| Select IC Randomly | `02` | `0f 01` | Maximum 15, minimum 1 |
| Customize Segment | `03` | `01 00` | One IC per segment, zero IC interval |

These are layer-record offsets `1:4`; they do not match the APK's internal enum order. All other
record bytes and the activation stayed byte-identical across the four marked Applies. Reapplying
Select IC Continuously produced the exact original body.

The final byte of each 29-byte layer record is priority. Default/disabled is `00`; setting only the
second copied layer to priority 2 changed only that byte to `02`. Copying and then deleting the
layer produced exact two-layer and one-layer A/B/A bodies.

All offsets below count the record length byte as `r0`. Four further marked captures isolated the
remaining visible field families:

| Current iOS control | Observed record change |
|---|---|
| Number of IC, Continuous | `r4: 0f -> 07` for 15 to 7 |
| Applied Area | `r1: 00 -> 50` for full 10/10 to 5/10; the app also clamps `r4` to `05` |
| Brightness Scope | `r7:r8: ff00 -> c639` for the displayed 22-77% range |
| Brightness Changing Speed | `r10: 7f -> ff` for displayed 50% to 100% |
| Brightest/Darkest retention | `r11:r12: 1414 -> c830` for displayed 200 and 48 |
| Distribution Method | `r13: 01 -> 00` for Based on Number of IC to Unified Color |
| Direction | `r13: 01 -> 81` for Forward to Backward |
| Colour Changing Speed / Retention | `r14:r15: 8014 -> ffff` for displayed 50%/20 to 100%/255 |
| Colour count | `r16: 02 -> 03`; the record length grows `r0: 1d -> 20` and the third RGB is appended |

The colour palette starts at `r17`. The seven trailing bytes after its variable-length RGB list
are three selected-area movement bytes, three overall-movement bytes and the priority byte.
With two colours:

- selected-area movement encoded `17 04 ff` for interval 4, Backward and Forward, 100% speed and
  Enter/Exit enabled;
- overall movement encoded `11 05 ff` for interval 5, Forward and Backward and 100% speed;
- disabled defaults are `00 00 80` before slider interaction and `00 00 7f` after returning a
  displayed 50% slider to its centre.

That `0x80` versus `0x7f` distinction also appears in the colour and brightness speed fields. It is
UI rounding, not a different displayed default. The marked captures are
`20260715135324-h617a-workshop-area-count-differential.pcap`,
`20260715140050-h617a-workshop-colour-family.pcap`,
`20260715141908-h617a-workshop-brightness-moving-effects.pcap` and
`20260715143430-h617a-workshop-selected-moving-completion.pcap`.

The field locations are now attributable, but an unrestricted encoder still requires the complete
packed value space for Applied Area, distribution/direction and movement flags, plus any priority
values and reorder behaviour needed beyond the proven default and level 2.

### rgbicv2 DIY (`TYPE 0x02`)

A per-segment **record container**, transported and activated exactly like a scene, so the
existing `build_scene_multi(base64(body[3:]), code)` reproduces a captured effect byte-for-byte.
Activation `33 05 04 <code_LE>` with a per-effect code (Brilliant 501, Colorful starry sky 502,
Colorful meteor shower 503, Colorful meteor 504, Sparkle 505, Bloom 506, Stack 507). The variant
(for example Bloom1 vs Bloom2) is a body byte, not a code change.

The body is `01 <linecount> 02`, then a 1-byte record count, then that many length-prefixed
records, then frame padding.

The record grammar is **confirmed** on the wire: the app's serialise and parse paths are exact
inverses. Each record is, with offsets from the record's own length byte:

```
offset  field          meaning
0       length         record length: number of bytes that follow
1       flags          packed nibbles (colour order / enable); 0x00 in the captures seen
2       type           mode selector 0-3; selects the meaning of offsets 3-4
3-4     value          type 0/1: signed 16-bit parameter (for example speed);
                       type 2: [max, min] byte pair (for example the star-size range);
                       type 3: a byte pair
5       bright mode    brightness sub-block prefix
6       bright count   N = number of 6-byte brightness records that follow
7..     brightness[N]  N x 6-byte records; the first two bytes are the relative-brightness
                       interval (upper, lower), each byte = round(pct x 2.55)

colour sub-block (immediately after the brightness records):
+0      colour byte    bit-packed: colour type / gradual (low nibble) and colour order;
                       bit 0 = direction-is-positive (forward vs reverse colour travel)
+1      colour param1  colour-cycle rate (set from the speed lookup)
+2      colour param2  secondary colour parameter
+3      colour count   M = number of RGB triples
+4..    RGB[M]         M x 3 bytes, distributed round-robin by colour index

in-area movement sub-block (3 bytes):
+0      packed         high nibble = enable, low nibble = mode 0-7
+1..+2  params         two movement parameters (one is the in-area speed)

whole-area movement sub-block (4 bytes):
+0      packed         high nibble = enable, low nibble = mode 0-3
+1..+3  params         three parameters (an overlay value when movement is off)
```

The V2 record variant (Bloom on this device, template id 113) appends, after the whole-area
block, a 1-byte param, a 1-byte length `y`, `y` bytes of blob and one trailing byte. Bloom's second
colour layer and numbered-variant byte live in this V2 region, including the observed body
offset 99.

A container holds one or more records; two-colour-group effects such as Bloom and Stack use
separate records for the base and moving layers, moved at independent rates. The movement engine
exposes four directions: Forward, Backward, Forward and Backward, and Backward and Forward
(`InAreaMoveEffectView` / `AllMoveEffectView`); a display speed 1-100 maps to the internal 1-255
(default 50). Motion is parameterised per record by a speed-mode lookup (`color`, `moveAll`,
`moveIn`, `bright` arrays plus `defaultIndex`), the client-side motion model. The type and value
bytes at offsets 2 to 4 and the brightness sub-block are decoded.

Still inferred (need a capture): the concrete per-effect speed-mode numeric arrays, the exact
pixel-level difference between numbered sub-styles (for example Brilliant `param2` `0x32` vs
`0x14`, Bloom `0x14` vs `0x16`), and the precise meaning of colour `param1` / `param2`. Per-effect
colour-group ranges, speed domains and directions are in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md) section 2.7. The full teardown is kept in
internal analysis notes.

### Finger Sketch DIY (`TYPE 0x03`)

```
EFFECT SPEED BRIGHT <bg RGB> <groupcount> [<segcount> <fill RGB> <segment index...>] ...
```

`EFFECT` is a motion code (Cycle `0x02`, Clockwise `0x09`, Counter-clockwise `0x0A`, Twinkle
`0x0F`, Gradient `0x13`, Breathe `0x14`); `SPEED` and `BRIGHT` are `0..100` bytes (`0x64` = 100);
then a background RGB and one or more paint groups. Each paint group is
`<segcount> <fill RGB> <segment index...>`, and segment indices are 0-based, matching the
colour-mask bit numbering. The body is sent as two `0xA3` frames (body in `idx=0x00`, empty
`idx=0xFF` terminator) and activated with `33 05 0a 20 03` (DIY select, slot `0x20`, TYPE `0x03`),
all confirmed live on firmware `3.02.24` (2026-07-16). Full detail in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md) section 2.4.

### Vibrant (`TYPE 0x03`)

An observed 14-byte preamble `01 05 03 09 00 64 01 01 01 0f 01 ff 00 00` (the leading `01 05 03`
being start marker, linecount and type), then 15 per-segment entries, each
`<segment_index> 01 <R> <G> <B>`. Activation `33 05 0a <slot>`. Vibrant is the static-gradient
member of the `TYPE 0x03` family: the bytes after the type are `09 00`, that is Finger Sketch
motion `0x09` (Clockwise) with the speed byte `0x00`. The 11 header bytes after the type are not
yet fully decoded (section 8). Confirmed by decoding a red-orange to yellow to green to blue
gradient: segment 0 red-orange, segments 6-7 yellow, segments 9-10 green, segment 13 blue.

## 7. Implementation status against protocol.py

| Command | Builder | Status |
|---|---|---|
| Power `33 01` | `build_power` | Confirmed live, byte-identical. |
| Whole-strip brightness `33 04` | `build_brightness` | Confirmed live, byte-identical, 1:1 linear. |
| Whole-strip colour `33 05 15 01` (mask `0x7FFF`) | `build_color_rgb` | Confirmed live, byte-identical. |
| Per-segment colour (arbitrary mask) | `build_segment_color` / `build_segment_paint` | Implemented and confirmed live (single-segment mask `0x0001`, all-segments `0x7FFF`). |
| Per-segment brightness `33 05 15 02` | `build_segment_brightness` | Implemented and confirmed live (single-segment mask). |
| Whole-strip white brightness `33 05 15 02` (mask `0x7FFF`) | `build_white_brightness` | Implemented and confirmed live; uses the all-segments mask `0x7FFF`. |
| Colour temperature `33 05 15 01 00 00 00 ...` | `build_color_temp` | Implemented and confirmed live; emits the true-Kelvin frame over 2000-9000K. |
| Scene select `33 05 04` | `build_scene` | Confirmed live. |
| Scene multi-frame `0xA3` | `build_scene_multi` | Confirmed live; carries the per-scene `scene_type` prefix (`0`/`1`/`2`). |
| Flat / Finger Sketch / Combo DIY `33 05 0a` + `0xA3` | `build_flat_diy` / `build_sketch` / `build_combo` | Implemented custom-effect builders. Finger Sketch body, two-frame `0xA3` framing and `33 05 0a 20 03` activation are directly validated on H617A firmware 3.02.24; the current Combo body and default slot `0xF0` are directly validated too. Flat remains capture-pinned. Slot read-back cannot identify the active body. |
| Workshop `0xA3` (`TYPE 0x02`) + `33 05 04 91 01 02` | none | Transport, minimum content, layers, Select Type, area/count, palette, timing, brightness, movement and priority field locations are mapped. Unproven packed value spaces remain fail-closed. |
| rgbicv2 DIY `33 05 04` + `0xA3` (`TYPE 0x02`) | `build_scene_multi` (transport) | Transport works: replay a captured `(body, code)` via `build_scene_multi`. No from-scratch builder yet. |
| Vibrant `0xA3` (type `0x03`) + `33 05 0a` | `build_vibrant` | Implemented from the capture-pinned header and per-segment gradient entries; remains experimental while the header is partly undecoded. |
| Music mode `33 05 13` | `build_music_mode_with_color` | Confirmed live. All 11 mode codes verified; builder handles mode + sensitivity + Dynamic/Calm + auto-colour (COUNT byte 6, `0` = auto on) + one manual colour. Capture-pinned per-mode `a3` templates and decoded controls are built in `build_music_params_a3`. |
| Video mode `33 05 00` | `build_video_mode` | H6199 only. Always emits the full frame `33 05 00 <region> <mode> <sat> <sound> <softness>`; softness persists when sound is off and is floored at `0x01`. |
| Video white balance `33 a9` | `build_video_white_balance` | H6199 raw two-axis frame only; no one-dimensional UI mapping. |
| Colour-mode query `aa 05` | `parse_color_mode_response` | Confirmed live, including DIY mode `0x0a` with its activation slot. |
| Scheduled timer write `33 23` | `build_timer_schedule` | Write confirmed live (4 slots, on/off, weekday bits Mon=bit0..Sun=bit6). |
| Timer table read-back `aa 23` | `parse_timer_schedule_table` | Decodes the full `ff`-prefixed 4-slot table into per-slot records; confirmed against the live reply. |
| Sleep / wake-up `33 11` / `33 12` | `build_timer_sleep` / `build_timer_wakeup` (+ parsers) | Builders shipped; replies captured live (OBSERVE). |
| Power-off memory | `build_poweroff_memory` / `parse_poweroff_memory` | Experimental and unsupported by both current model profiles. No H617A app surface or live frame is proven. |
| Clock sync `33 09` | none | Informational; not needed for control. |

Remaining gaps:

- **App-authored DIY read-back**: no device query returns the full editor body, so an
  app-authored DIY cannot be imported from the strip.
- **Segment read-back request**: `aa a5` replies are decoded, but the app request that elicits each
  group is not captured.
- **Music per-mode parameters**: capture-pinned parameter builders exist, but the remaining
  controls are not all exposed as entities.

## 8. Evidence gaps

The remaining H617A work is bounded:

- capture the request that elicits each `AA A5` segment reply;
- complete Workshop packed enums, movement flags, priorities, and layer reorder behaviour;
- finish rgbicv2 per-effect parameter maps and from-scratch authoring;
- establish one current adjustable-scene editor path before testing scene parameters;
- verify the remaining music controls and read-back semantics;
- complete semantic validation of the experimental Flat and Vibrant builders.

The authoritative ordered backlog is
[`ble-protocol-open-questions.md`](ble-protocol-open-questions.md). Effect identities and parameter
domains are in [`ble-effect-catalogue.md`](ble-effect-catalogue.md).
