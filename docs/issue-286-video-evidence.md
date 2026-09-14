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

## Firmware Identity

- `pact_h6099/detail/mode/VideoVm.java:72-76` passes `info.n0()` to
  `pact_h6099/pact/Support.java:319-320`. For H6099, that example requires
  `NumberUtil.parseVersion(version) >= 10011` for border removal.
- `base2light/kt/comm/Info4BleIotDevice.java:650-651` returns field H;
  line 450 assigns H to `BleIotInfo.wifiSoftVersion`.
- `base2light/ble/controller/WifiSoftVersionController.java:12,30-32`
  reads opcode 0x21. `WifiHardVersionController.java:12,30-32` reads 0x20.
  Integration fields remain `subordinate_21_version` and `subordinate_20_version`.
- `base2home/util/NumberUtil.java:385-392` removes dots then parses an integer;
  `shared/utils/KmpVersionUtils.java:22` defines the delimiter as `.`.
  Missing/malformed identity is an evidence gap here, not the app's numeric zero.

No shipped profile has a firmware condition. Tests use a deliberately unrelated
`9.08.07` threshold on an already-declared synthetic white-balance control.
The H6099 border-removal threshold is not transferred to any runtime control.
Conditions can only narrow an existing per-model capability. The existing device
subscription publishes updated control states after identity notifications.
Recovery retains old documents unchanged; new profile transactions persist their
requested control set so omitted registers are not restored as incidental writes.
