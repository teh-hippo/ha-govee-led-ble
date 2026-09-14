# Video Semantics Evidence

Base: #285, `13e12f4418200a8cbc8bc137edcba26831b38dd9`.
Source: Govee Android 7.6.01, locally decompiled under
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources`.

- `com/govee/base2light/relativebrightness/controller/RelativeBrightnessController.java:87-116`
  selects count 4 or 6 and writes selector 1 plus six slots under AE. Existing
  H6199 Kaitai names identify left/top/right/bottom/strip-left/strip-right.
- `com/govee/pact_h6099/ble/controller/Controller4WhiteBalance.java:30-37,71-74`
  writes A9 selector 6, length 1, scalar; its parser reads that scalar after
  selector and length. This establishes encoding, not its user range or calibration.
- The H6199 20-position calibration and default 17 remain unchanged. Its ordered
  topology is explicitly four edges; the additional wire slots remain zero.
- Test-only H7000 uses an artificial three-value scalar calibration and six zones
  through the real generated parser/writer. This is not H6099 authorization,
  calibration evidence, or qualification of six-zone hardware.

No H6099 profile, border-removal control, or physical device support is enabled.
