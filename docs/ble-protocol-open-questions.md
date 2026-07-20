# Govee BLE protocol verification backlog

This is the current evidence backlog for the supported H617A and H6199 devices. Confirmed layouts
belong in [`ble-protocol-h617a.md`](ble-protocol-h617a.md) and
[`ble-protocol-h6199.md`](ble-protocol-h6199.md). Effect content belongs in
[`ble-effect-catalogue.md`](ble-effect-catalogue.md). The operating method is defined in
[`ble-capture-workflow.md`](ble-capture-workflow.md).

An item closes only when its app action is attributable, the predicted and observed BLE frames are
compared, the relevant reply or physical state is checked, and the baseline is restored.

## Priority backlog

| Priority | Scope | Gap | Required closure evidence |
| --- | --- | --- | --- |
| P0 | H617A verification | Core commands need one coherent prediction-first regression campaign. | Marked iPhone-driven checks for power, colour, music, and built-in scenes, followed by owner review before broader coverage. |
| P0 | H617A segment read-back | Resolved 2026-07-17 (firmware 3.02.24): opening the Color control makes the app issue five per-group queries `aa a5 01`-`aa a5 05` (zero-padded, XOR checksum; group 1 = `aa a5 01 00…00 0e`), each answered by the matching `aa a5 <group>` reply, plus a trailing `aa a3 00` multi-frame probe. Documented in `ble-protocol-h617a.md`. | Closed. |
| P0 | H6199 video | Resolved 2026-07-16 (commit `4c6ecce`): `build_video_mode` always emits the full 8-byte frame `33 05 00 <region> <mode> <sat> <sound> <softness>` with softness floored at `0x01`; byte-pinned for sound-off-with-retained-softness and minimum softness, with coordinator expectations updated. | Closed. |
| P0 | H6199 colour temperature | The shared builder is H617A-validated; no attributable H6199 colour-temperature action is retained. | Capture the current app frame and compare the complete payload with `build_color_temp`. |
| P1 | H617A Workshop | Field locations mapped; `r13` distribution/direction packing resolved (2026-07-16, `0x80` Backward OR-ed with distribution `00`/`01`/`02`). Movement, priority and layer-reorder value spaces remain. | Rerun, diffing each Apply against a known baseline, one field per marked window: (1) the three selected-area and three overall movement bytes across each flag/direction toggle; (2) priority values above 2; (3) drag-reorder two layers and diff record order; (4) the Color-gradient toggle body delta under Based on Segment. |
| P1 | H617A rgbicv2 DIY | Transport, record grammar, all speed handles, Stack brightness, and meteor/shower/Stack directions are mapped (2026-07-20, commit `6916ef9`). Remaining: from-scratch per-effect authoring and the `param2` sub-style delta. | Synthesise a body from scratch and byte-compare it with a captured effect; isolate the `param2` pixel-level difference between numbered sub-styles. |
| P1 | H617A adjustable scenes | Resolved 2026-07-16: the editor is the per-scene edit pencil; Speed + Color Change re-upload a modified body via `build_scene_multi` (Aurora A/B/A byte-exact, offsets 18/68). | Closed. |
| P1 | H617A music | All 11 mode IDs and several parameter offsets are confirmed, but the full app surface and read-back semantics are incomplete. | Verify each exposed colour, style, direction, count, speed, gradient, and relative-brightness control against its predicted frame. |
| P1 | H6199 video status | No attributable `AA 05` video reply exists. | Capture video mode activation and the following status reply in one marked window. |
| P1 | H6199 white balance | Raw red and blue bytes are independent; UI coordinates and ranges are unknown. | Capture isolated red-axis and blue-axis A/B/A movements without fitting a one-dimensional model. |
| P1 | H6199 scenes | Scene transport and catalogue data exist, but the runtime surface is disabled. | Verify representative simple and A3 scenes, then prove generated catalogue parity before exposure. |
| P1 | H6199 DIY | Fade1 proves flat DIY exists and activates through slot `0x61`; other families and parameters are unknown. | Capture speed A/B/A and at least one second family before defining a model-specific encoder. |
| P1 | H6199 segments | The device reports 15 segments, but no write is attributable. | Capture a vendor-app segment write before enabling services or custom effects. |
| P1 | H6199 white brightness | The exposed `33 05 15 02 ... FF 7F` surface is inherited from H617A and unvalidated on H6199. | Capture the vendor app's whole-device white-brightness action or disable the surface. |
| P2 | H6199 music | Only mode and sensitivity are proven for the four classic modes. | Determine whether style, manual colour, count, or extended parameter frames exist on this model. |
| P2 | H6199 advanced controls | Blank Screen inner fields, per-side brightness, and other `0xA9` controls remain undecoded. | Use one control family per marked app-sniff and retain independent A/B/A evidence. |
| P2 | Unsupported features | H6199 timers and power-off memory have no current-device evidence. | Keep them disabled unless the current app exposes them and attributable captures prove their frames. |

## Known protocol limits

- `AA 05 0A <slot>` identifies only the active DIY slot. It does not return the A3 body or prove
  which application authored it.
- No known query imports an app-authored DIY body from the device. Treat this as a device limit
  unless new evidence appears.
- H6199 validation is app-sniff only. Development tools must not direct-drive it.
- A catalogue payload proves what the service publishes, not that the current account exposes an
  editor for every parameter.
- A simulated validation run proves internal consistency only. It is not device evidence.

## Closed items

The following results are settled and should not be reopened without contradictory captures:

| Scope | Result |
| --- | --- |
| H617A music IDs | Energetic `05`, Rhythm `03`, Spectrum `04`, Rolling `06`, plus extended modes `30` to `35` and `37`. |
| H617A timer weekdays | Monday is bit 0 through Sunday at bit 6. |
| H617A whole-strip mask | All 15 segments is `0x7FFF`; builders do not use `0x0000`. |
| H617A colour temperature | `33 05 15 01` carries Kelvin at `[7:9]` and drives true white over 2000 to 9000 K. |
| H617A timer queries | `AA 11`, `AA 12`, `AA 14`, and `AA 23` are sleep, wake-up, gradual, and the four-slot timer table. |
| H617A Combo | One to four steps, shared palette and speed, sequence length, editor behaviour, and slot `0xF0` acceptance are proven. Slot ownership is not. |
| H617A Workshop transport | A3 type `02`, length-delimited layer records, and activation `33 05 04 91 01 02` are proven. |
| H6199 identity | Hardware query is `AA 07 03`; captured hardware is `3.02.01`. |
