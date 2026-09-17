# Global Scope Policy

The [repository non-goals](../CONTRIBUTING.md#repository-non-goals) apply to all
models and runtime surfaces, not just H6099 or its support issue
[#258](https://github.com/teh-hippo/ha-govee-led-ble/issues/258).

| Feature | Policy |
| --- | --- |
| AI filter | No runtime selector, configuration, query, readback, or recovery support, even when BLE encoding is known. |
| Wi-Fi provisioning and cloud communication | Documentation-only known wire layouts; no credential handling, provisioning workflow, account setup, or cloud device control. |
| Onboard timers, countdowns, wake/sleep schedules | Documentation-only known wire layouts; no runtime queries, writes, or clock synchronization for scheduling. Use Home Assistant automations. Integration retry/lease timers are unrelated. |
| Phone/host microphone | No capture, injection, or audio-derived control. Onboard device-microphone modes remain in scope. |
| Firmware/OTA | Excluded for device safety. Reading firmware identity for capability qualification is not an update workflow. |
| Cloud camera image calibration | No cloud/Wi-Fi snapshot acquisition, image-point upload, or calibration workflow. BLE installation direction and white balance are explicitly not excluded; qualify their capabilities separately. |

Existing continuous host streaming and manufacturer-style animated-preview
non-goals also remain unchanged. Inert scene catalogues and developer catalogue
refresh are not runtime cloud device control.

Provisioning/cloud exchanges are not currently decryptable into a usable,
qualified workflow with the available evidence and implementation. This is not
an assertion that decryption is inherently impossible: some payload layouts
are known, and local BLE encryption support does not establish cloud protocol,
credentials, or exact provisioning branch compatibility. The runtime exclusion
is a scope decision, independent of future protocol research.

## App Evidence

Source: Govee Android 7.6.01, decompiled at
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources`.
Paths below are relative to `sources/com/govee/`. Static code establishes app
layouts and routes, not successful H6099 transport or physical compatibility.

- Wi-Fi: `pact_h6099/add/WifiChooseAc.java:31,152-155` inherits the shared
  provisioning activity and supplies its BLE instance.
  `base2light/ac/AbsBleWifiChooseActivity.java:1503-1515` selects
  `MultipleWifiController` and optional extensions before dispatch.
  `base2light/ble/controller/MultipleWifiController.java:22-105` emits byte-length
  prefixed SSID/password, run mode, timezone hour, IoT version, and timezone minute.
  The API branch appends a two-byte length and API bytes; `x`/`y` at lines 166-198
  append branch-dependent Matter/security bytes. The
  `speculative/h6099_wifi_provision_body.ksy` models the common reassembled prefix,
  preserving the optional suffix: exact H6099 branch selection is unqualified.
  Existing H6199 Wi-Fi schemas remain H6199 evidence, not a whole-model alias.
- Timers: `pact_h6099/ble/controller/compose/TimerController.java:26-40,66-69`
  specifies opcode `0x23`, a one-byte query index (`0xff` for all), and a write
  index followed by enable/type, hour, minute, and repeat bytes.
  `ParserTimers.java:15-28` and `ComposeReadTimerAllInfo.java:37-55` skip one
  reply-body byte and read four four-byte records. The
  `speculative/h6099_onboard_timer_payload.ksy` records only these payloads.
  `AbsController.java:24-27` uses the shared frame builder;
  `base2light/ble/controller/AbsControllerNoEvent4Single.java:153-159,235-240`
  selects write `0x33` / read `0xaa` and extracts the 17-byte reply body.
  No single-index reply, countdown, wake/sleep, or encrypted envelope is inferred.
- AI: `base2light/videomode/newdetail/controller/AiFilterController.java:45-72,98-101`
  writes and reads opcode `0xa9`, selector `0x10`.
  `pact_h6099/detail/NewDetailVm.java:669-677` conditionally adds its query and
  `detail/mode/VideoMode.java:139-140` adds the UI. Known BLE transport does not
  make this in scope. No AI-filter schema or runtime capability is implemented.
- Camera images: `pact_h6099/add/camera/CalibrationReadM.java:209-235` checks
  network/IoT availability and requests a snapshot over IoT;
  `CalibrationAc.java:315-324` submits image URL and calibration points.
  This exclusion is distinct from
  `ble/controller/compose/DirectionController.java:25-32,56-59` (BLE opcode
  `0x30`) and `ble/controller/Controller4WhiteBalance.java:30-37,71-74`
  (`0xa9`, selector 6). Their encoding does not establish values/ranges or
  authorize a profile, but neither feature is globally excluded.

Both payload schemas live under `tools/ble/kaitai/speculative/`, begin with
`SPECULATIVE`, and are documentation-only. Do not add them to runtime roots,
imports, builders, services, queries, or recovery. Unknown layouts stay gaps.
Never use real credentials, addresses, images, or device identifiers in fixtures.

## Runtime Audit

The source audit finds no runtime AI-filter implementation: no profile
capability, selector/configuration, query, status interpretation, UI, or
restored-state/recovery field. Case-insensitive searches for `AI`, `AiFilter`,
`ai_filter`, and filter/AI combinations cover integration Python, frontend
TypeScript, service/translation declarations, and Kaitai sources. Inspection
of the `A9` display-setting enums and routing also finds no AI selector `0x10`;
unrelated `0x10` bit flags and dependency sponsor URLs are not AI controls.

The H6099 Wi-Fi and onboard-timer payload schemas are absent from
`scripts/kaitai-runtime-roots.txt` and runtime imports/builders/services.
Runtime source contains no scheduling clock-sync path. App-only
`AiFilterController` remains outside the integration. Keep this boundary when
extending profiles, protocol routing, UI, queries, and recovery: a known app
opcode does not authorize runtime support.

## Schema Check

Compile documentation schemas outside runtime outputs, then parse synthetic
payloads and verify truncation rejection. From the repository root, with the
locked development environment installed:

```bash
bash scripts/generate-kaitai.sh all /tmp/opencode/h6099-policy-kaitai
PYTHONPATH=/tmp/opencode/h6099-policy-kaitai uv run --no-sync python -c '
from h6099_wifi_provision_body import H6099WifiProvisionBody as Wifi
from h6099_onboard_timer_payload import H6099OnboardTimerPayload as Timers

def parse(parser, payload):
    result = parser.from_bytes(payload)
    result._read()
    return result

wifi = bytes.fromhex("036c61620001ff0200000241420103")
w = parse(Wifi, wifi)
assert (w.ssid, w.password, w.run_mode) == (b"lab", b"", 1)
assert (w.timezone_hour_raw, w.iot_version, w.timezone_minute_raw) == (255, 2, 0)
assert w.extension_raw == bytes.fromhex("000241420103") and w._io.is_eof()
assert parse(Wifi, wifi[:9]).extension_raw == b""
records = bytes.fromhex("810617fe0008170001172a7f80003b80")
t = parse(Timers, b"\x7e" + records)
assert [(r.enable_and_type_raw, r.hour, r.minute, r.repeat_raw) for r in t.timers] == [(129, 6, 23, 254), (0, 8, 23, 0), (1, 23, 42, 127), (128, 0, 59, 128)]
assert t.unknown_prefix == 126 and t._io.is_eof()
assert parse(Timers.QueryPayload, b"\xff").index == 255
p = parse(Timers.WritePayload, b"\x02" + records[:4])
assert (p.index, p.timer.hour, p.timer.minute, p.timer.repeat_raw) == (2, 6, 23, 254)
for parser, payload in [(Wifi, wifi[:8]), (Timers, records), (Timers.QueryPayload, b""), (Timers.WritePayload, b"\x02\x81")]:
    try:
        parse(parser, payload)
    except EOFError:
        pass
    else:
        raise AssertionError("truncated payload accepted")
print("Wi-Fi and timer documentation payload checks passed")
'
```

These checks prove parser structure only, not checksum handling, encryption,
device acceptance, or physical behaviour. No provisioning, timer operation,
cloud request, microphone capture, or OTA operation is needed for validation.
