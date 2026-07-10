# Govee H617A BLE protocol: open questions and verification backlog

The single worklist of what is still unverified or undiscovered in the H617A BLE protocol. Each
item states what is known, what is uncertain, and how to close it. The confirmed protocol lives
in [`ble-protocol-h617a.md`](ble-protocol-h617a.md) and the effect catalogue in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md); the capture method is in
[`ble-capture-workflow.md`](ble-capture-workflow.md).

Priority order below is roughly the order to work through them.

> **Update 2026-07-08 (protocol analysis).** A round of live BLE capture and protocol analysis closed
> items **2 (query semantics)** and **6 (timer map)** outright, largely closed **1 (music)** apart
> from a version-dependent classic-band code, and reframed **5 (rgbicv2 numerics)** as a cloud
> effect-library fetch rather than more on-wire capture. The remaining device-behaviour items are best
> closed with the new guided **live validation harness** `tools/ble/validate_protocol.py` (prompts
> one action at a time, watches the sniff, and diffs the app's frame against our `protocol.py`).

> **Update 2026-07-10 (live app-sniff capture) — remaining items CLOSED.** The daytime capture
> session closed the outstanding device-behaviour items:
> - Item 1: music classic-band codes are **{Energetic 5, Rhythm 3, Spectrum 4, Rolling 6}**; `byte[5]`
>   is style (Rhythm dynamic 0 / calm 1) and `byte[6]` is colour count (0 = auto). Encoder confirmed.
> - Items 2/6: timer `repeat` weekday order is **Mon=bit0 … Sun=bit6** (Mon-only `0x81`, Sun-only `0xC0`).
> - Item 3: **moot** — the integration uses mask `0x7FFF` everywhere, so no builder emits `0x0000`.
> - Item 4: colour-temp reads back as its white-point RGB with **no kelvin field**; the coordinator now
>   recognises that and keeps CT mode instead of dropping to RGB (fixed).
> - Per-segment read-back frame decoded: **`aa a5 <group 1-5> + 3×[bri,R,G,B]`**, 15 segments.
> - H6199 encoders validated (see `ble-protocol-h6199.md`); power-off memory is not an H617A feature
>   (its app has no such setting).
> Remaining work is the DIY authoring UI and wider multi-SKU capture, not protocol gaps.

## 1. Music mode, per-mode parameters (mostly CLOSED; classic-band codes need live confirm)

Fully mapped by live capture. See `ble-protocol-h617a.md` "Music mode layout" for the
authoritative table. **Remaining uncertainty:** the classic-band mode codes
(Energetic/Rhythm/Spectrum/Rolling) differ across app versions/variants: earlier analysis gave
{0,5,3,2} and {16,17,18,19}, and the on-wire capture gave {5,3,4,6}. The
extended band (0x30-0x37) is certain. Close by direct-drive on the H617A (harness section F).
What is **not** yet established is each mode's control surface, because only Rhythm and Energetic
were exercised in depth:

- Which of the 11 modes expose a **colour picker** at all, versus Auto-color-only? (Confirmed
  with colour: Energetic `0x05`, Rhythm `0x03`. The other nine are unchecked.)

Per-mode control surface is now known from the app's edit widgets: movement modes expose
segment/point count, speed, direction, gradient; simple modes only Dynamic/Calm + auto-colour +
one colour. Remaining small unknowns: whether code `0x36` is a real 12th mode (absent from the app
table, likely unused), and the exact per-mode default values. The **"From phone" sound source**
needs no special frame: the app runs a client-side animator and streams standard colour frames.

## 2. Query semantics (`aa 11`, `aa 12`, `aa 14`, `aa 23`) — CLOSED

Resolved by live capture: all four are the
timer subsystem, not segment/IC config.

- `aa 11` = **Sleep timer** `[enable, startBri, closeMin, curMin]`.
- `aa 12` = **Wake-up timer** `[enable, endBri, hour, min, repeat, rampMin]`.
- `aa 14` = **Gradual** on/off toggle; returns nothing when unset.
- `aa 23` = **Timer table**, 4 on/off slots.

See `ble-protocol-h617a.md` "Timer subsystem" for the byte layouts. Only the `repeat` weekday
bit order (item 6) remains.

## 3. Segment mask `0x0000`

`33 05 15 01` (colour) and `33 05 15 02` (per-segment brightness) carry a 16-bit segment mask.
All 15 segments is `0x7FFF`; single-segment and alternating masks are confirmed (the app's Random
Color uses them). Unknown: whether **`0x0000` means all segments or no segments**. The current
`build_white_brightness` emits `0x0000`, so this decides whether that builder is a no-op.

How to close: direct-drive `33 05 15 02 <pct> 00 00` and read back with `aa a5`; likewise for a
`15 01` colour with mask `0x0000`. Needs the strip free (phone Bluetooth off, HA entry disabled).

## 4. Colour temperature on the device

The frame is known: `33 05 15 01 00 00 00 <Khi> <Klo> <R> <G> <B> <ML> <MH>`, Kelvin big-endian at
`[7:9]`, Govee's white RGB at `[9:12]`. Five curve points are measured (2000 K `FF8D0B`, 3000 K
`FFB969`, 4300 K `FFDBAF`, 5300 K `FFEBD7`, 9000 K `D9E1FF`).

Unknown / to do:

- Confirm the corrected frame actually drives **true white mode** on the strip (not an RGB
  approximation), by driving it and reading back the colour mode.
- Extend the **Kelvin-to-white-RGB curve** beyond five points if the integration is to render its
  own intermediate values rather than replay captured ones.

How to close: direct-drive at several Kelvin values and read back; or capture more app slider
positions.

## 5. rgbicv2 DIY per-effect fields

The record grammar is fully decoded
([`ble-protocol-h617a.md`](ble-protocol-h617a.md) section 6). The per-effect **numeric values are
not carried on the wire**: the speed-mode arrays (`color`/`moveAll`/`moveIn`/`shuiBoWen*`/`bright`)
are deserialised from the **cloud effect-library JSON**. So this item is not more on-wire capture;
it is:

- Fetch and catalogue the cloud effect library (tooling exists: `tools/ble/fetch_effect_library.py`)
  to get the speed-mode arrays and `defaultIndex` per H617A effect.
- The numbered sub-style bytes, direction value space, and colour `param1`/`param2` are then read
  from those templates (or confirmed on-wire with the live harness).

## 6. Timer subsystem — CLOSED (one small item left)

Fully mapped by live capture (sleep, wake-up, gradual and the 4-slot timer table). Layouts in
`ble-protocol-h617a.md` "Timer subsystem": `0x23` = 4 on/off slots
`[idx, enableAndType, hour, min, repeat]` with `enableAndType` bit7=enabled/bit0=on-off; `0x11`
sleep; `0x12` wake-up; `0x14` gradual. **Only remaining unknown:** the `repeat` weekday bitmask
bit order (which bit = Monday). Close by setting two distinct day patterns via the live harness and
diffing.

## 7. Closed / not applicable (recorded so we do not re-chase)

- **Color Slider** (More menu): a plain colour picker; emits the standard `33 05 15 01 <RGB>`
  whole-strip frame. No new command.
- **Random Color** (More menu): a per-segment random palette; each "Next" applies ~15 per-segment
  `33 05 15 01` frames. No new command, but it confirmed arbitrary per-segment masks on the wire.
  Note: a `33 a3 00 ...` frame precedes the batch — likely a segment-write marker, worth a glance
  but low value.
- **Snapshot** (More menu): an app-side store of saved looks ("No snapshots yet" by default);
  applying one replays the underlying colour/scene/effect command. No new command.
- **Video mode**: not offered for the H617A in the app (an H6199 TV-backlight feature).
  `build_video_mode` / `build_video_white_balance` stay builder-derived and cannot be validated on
  this SKU without an H6199.

## 8. Tooling and provenance notes

- Live capture needs the iPhone's Apple Bluetooth logging profile **active** (reinstall + reboot
  if `idevicebtlogger` streams 0 bytes). Decoding runs in WSL; only capturing needs Windows.
- Direct-drive verification uses `tools/ble/govee-send.py` on the Windows host, with the strip's
  single BLE connection freed (phone Bluetooth off and the HA config entry disabled).
- The Music, flat and Combo parameter models here come from on-wire capture. Wider live capture
  across more SKUs would give an authoritative, all-SKU parameter model (music modes, flat/combo
  encoders, timer fields) and is the belt-and-braces way to close items 1, 5 and 6.
