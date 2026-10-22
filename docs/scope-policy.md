# Global Scope Policy

The [repository non-goals](../CONTRIBUTING.md#repository-non-goals) apply to all
models and runtime surfaces, not just H6099 or its support issue
[#258](https://github.com/teh-hippo/ha-govee-led-ble/issues/258).

| Feature | Policy |
| --- | --- |
| AI filter | No runtime selector, configuration, query, readback, or recovery support, even when BLE encoding is known. |
| Wi-Fi provisioning and cloud communication | Documentation-only known wire layouts; no credential handling, provisioning workflow, account setup, or cloud device control. |
| Onboard timers, countdowns, wake/sleep schedules | Documentation-only known wire layouts; no runtime queries, writes, or clock synchronisation for scheduling.  Use Home Assistant automations.  Integration retry/lease timers are unrelated. |
| Phone/host microphone | No capture, injection, or audio-derived control.  Onboard device-microphone modes remain in scope. |
| Firmware/OTA | Excluded for device safety.  Reading firmware identity for capability qualification is not an update workflow. |
| Cloud camera image calibration | No cloud/Wi-Fi snapshot acquisition, image-point upload, or calibration workflow.  BLE installation direction and white balance are explicitly not excluded; qualify their capabilities separately. |

Existing continuous host streaming and manufacturer-style animated-preview
non-goals also remain unchanged.  Inert scene catalogues and developer catalogue
refresh are not runtime cloud device control.

Provisioning/cloud exchanges are not currently decryptable into a usable,
qualified workflow with the available evidence and implementation.  This is not
an assertion that decryption is inherently impossible: some payload layouts
are known, and local BLE encryption support does not establish cloud protocol,
credentials, or exact provisioning branch compatibility.  The runtime exclusion
is a scope decision, independent of future protocol research.

## App Evidence

Govee Android 7.6.01 behaviour establishes candidate payload layouts and routes,
not successful H6099 transport or physical compatibility.

- Wi-Fi: the shared multi-packet provisioning body emits byte-length-prefixed
  SSID and password fields, run mode, timezone hour, IoT version, and timezone
  minute, followed by branch-dependent API, Matter, or security extension bytes.
  `speculative/h6099_wifi_provision_body.ksy` models the common reassembled
  prefix and preserves the optional suffix because exact H6099 branch selection
  is unqualified.  Existing H6199 Wi-Fi schemas remain H6199 evidence, not a
  whole-model alias.
- Timers: H6099 onboard timer control uses opcode `0x23` (`0x33` write / `0xaa`
  read) with a one-byte query index (`0xff` for all) and a five-byte write body
  (index followed by enable/type, hour, minute, and repeat bytes).  Read-all
  replies skip one prefix byte and carry four four-byte timer records across the
  17-byte reply body.  `speculative/h6099_onboard_timer_payload.ksy` records only
  these payloads; no single-index reply, countdown, wake/sleep, or encrypted
  envelope is inferred.
- AI: the app writes and reads AI filter state on opcode `0xa9`, selector `0x10`.
  Known BLE transport does not bring this feature into scope, and no AI-filter
  schema or runtime capability is implemented.
- Camera images: camera snapshot calibration checks network/IoT availability,
  requests a cloud snapshot over IoT, and submits an image URL with calibration
  points.  This exclusion is distinct from BLE installation direction (opcode
  `0x30`) and scalar white balance (opcode `0xa9`, selector `0x06`), whose
  encodings do not establish value ranges or authorise a profile, though neither
  feature is globally excluded.

Both payload schemas live under `tools/ble/kaitai/speculative/`, begin with
`SPECULATIVE`, and are documentation-only.  Do not add them to runtime roots,
imports, builders, services, queries, or recovery.  Unknown layouts stay gaps.
Never use real credentials, addresses, images, or device identifiers in fixtures.
