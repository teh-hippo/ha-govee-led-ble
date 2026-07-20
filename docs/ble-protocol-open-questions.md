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
| P1 | H617A rgbicv2 DIY | Transport, record grammar, all speed handles, Stack brightness, and meteor/shower/Stack directions are mapped. The `param2` sub-style delta between numbered variants is still inferred. | Isolate the `param2` pixel-level difference between numbered sub-styles with colours held fixed. |
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
