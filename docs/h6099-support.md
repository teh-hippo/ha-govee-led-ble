# H6099 Support

## Request and Known Context

[Issue #258](https://github.com/teh-hippo/ha-govee-led-ble/issues/258) requests
H6099 TV Backlight 3 Lite support. The exact-model profile is **Experimental**:
implemented candidate controls are not owner-qualified hardware support.
Android app code, catalogue data, and synthetic tests do not prove device
acceptance, visible behaviour, or restoration on an owner's firmware.

This document follows the [contributor model plan](../CONTRIBUTING.md#planning-support-for-a-new-model).
The [global scope policy](scope-policy.md) and
[support lifecycle](../CONTRIBUTING.md#support-lifecycle) apply, with the explicit
maintainer-approved 7.6.0 inclusion exception described below.
H6099 has its own profile, grammars, capability
contract, and catalogue; it is not an H6199 profile alias.

The owner [reported successful connection on v7.6.0-rc.1.h6099](https://github.com/teh-hippo/ha-govee-led-ble/issues/258#issuecomment-5681092324).
Control, rendering, readback and restoration qualification remain outstanding;
the report does not identify hardware or firmware versions. The maintainer
approved inclusion in stable 7.6.0 while retaining Experimental status and
speculative schemas. H6099 requires manual addition or reconfiguration; no
automatic-discovery matcher is registered for this model.

## Research Findings

The static source reference is Govee Android **7.6.01**, principally
`sources/com/govee/pact_h6099/`, with goods type **191**. Shared classes are
evidence only where the exact H6099 route calls them. Sources were inspected
from the decompiled `h6125-7.6.01/full` tree; that directory name does not
establish H6125/H6099 compatibility. No attributable H6099 official-app BLE
capture or successful owner qualification is claimed here.

| Evidence | Finding and Repository Representation |
| --- | --- |
| `detail/Info4Detail`, `ble/v1/SubModeColorV1`, `ble/v1/Sub4Diy`, `pact/Support` | Static Kelvin readback, separate rendered RGB pages, 14 logical zones, and DIY selector. [Command](../tools/ble/kaitai/speculative/h6099_command_write.ksy), [query](../tools/ble/kaitai/speculative/h6099_status_query.ksy), and [status](../tools/ble/kaitai/speculative/h6099_status_reply.ksy) roots model logical frames. |
| `detail/diy/H6099DiyConfig`, `DiyProtocolParseShare0x00`, `RgbIcGraffitiShare0x08`, `DiyNewEditVm` | Ordinary Basic/Mixed type `04` and Graffiti type `03`, with default `Sub4Diy` code 254. [Effect root](../tools/ble/kaitai/speculative/h6099_effect_upload.ksy) reuses the shared body structures, not an H6199 activation carrier. |
| `detail/mode/MusicMode.d`, `MusicEffect`, `SubMusicModeConfig`, shared `RgbMusic*` / `RgbicMusic*` controllers | Eleven selectors, A3 `41` companion before mode selection, mode-specific parameters and 1-8 palette colours. [Music root](../tools/ble/kaitai/speculative/h6099_music_parameters.ksy) preserves unresolved Day/Night and Energetic paths. |
| `ControllerIcNum`, `NewDetailVm$connectBleSuc$1`, `Info4BleIotDevice.q()` | `AA 40` returns signed big-endian physical IC count. Logical zone count is not a substitute. |
| `detail/mode/VideoMode`, `VideoVm`, `pact/Support.supportBorderRemove`, `PairAcV1` | Video controls and border threshold from Wi-Fi software identity. Shared `SaturationViewInterface.getSaturationView` specifies saturation 1-100. |
| `ble/controller/compose/DirectionController`, `ComposeCalibrationDirection`, `HasCameraController` | Standalone direction `30` and camera health `32`. `Adapter4CalibrationDirection` offers values 3, 4, 2, 5; resource names do not establish corner labels. Shared `VideoModeViewInterface` / `AbsVideoMode` distinguish camera values 0, 1, 2. `CameraPosController` is separate opcode `31`. |
| `Constant.movieFeastVersion`, `Constant.maxSubDeviceNumMovie`, `Area4Device.j`, `MovieOpenControllerV2`, `FeastBrightnessUniteController`, `moviefeast/ble/controllerV2` | MovieFeastV2, seven sub-devices, bounded A3 `50` group upload, and individual module `60` settings. [Group](../tools/ble/kaitai/speculative/h6099_dreamview_group.ksy) and [frame](../tools/ble/kaitai/speculative/h6099_dreamview_frame.ksy) roots do not establish membership readback. |
| `com/govee/encryp/ble` controllers `Controller4Aes`, `Safe`, `Controller4AesGcm`; `BleUtil.parseBleBroadcastPact` | Shared V1 and limited V2 encryption hypothesis, represented in [encryption KSY](../tools/ble/kaitai/speculative/govee_encryption.ksy). Exact H6099 transport remains unqualified. |

The committed [H6099 240-scene catalogue](../custom_components/ha_govee_led_ble/scene_catalogues/H6099.json)
is exact-SKU vendor metadata. It establishes identities and payload data, not
upload, activation, readback, or restoration compatibility. See the
[catalogue evidence rules](../CONTRIBUTING.md#exact-sku-scene-catalogues).

## Candidate Support Scope

### Basic Light, Identity, and Scenes

- Power, brightness, RGB, 2000-9000 K colour temperature, and colour/brightness
  writes to logical segments 1-14 are implemented. The whole-device mask is
  `0x3fff`; segment reads use four-slot pages, with unused final records opaque.
- `AA 05 15` reports a flag and big-endian Kelvin; zero means RGB mode, not a
  black RGB colour. Rendered RGB requires the segment replies. Command echoes
  and optimistic entity state are not observations.
- Firmware/hardware identity uses `AA 06` / `AA 07`; Wi-Fi hardware/software
  identity uses `AA 20` / `AA 21`. Missing identity is retried within the bounded
  coordinator identity loop. Setup requires only power, brightness, and colour
  mode replies, not optional installation controls or physical IC discovery.
- Physical IC count (`physicalIC` in the app, `physical_ic_count` in the
  integration) starts unknown and accepts only positive `AA 40` values. It is
  device/connection-scoped, cleared on disconnect/reconnect, and never inferred
  from the 14 logical zones. Dependent requests recheck geometry before writes.
- Identity reads do **not** synchronize the clock. No runtime time-sync path is
  implemented, and a requirement for time sync before ordinary light control
  has not been proven. The app's timer composition uses `SyncTimeController`;
  that is not evidence to enable scheduling or add a light-setup dependency.
- All 240 native catalogue scenes have a candidate activation path, including
  applicable bounded type-1/type-2 uploads. Scene selection/readback alone does
  not prove the uploaded payload is rendered correctly.

### Ordinary DIY and Effect Studio

Basic, Mixed, and Graffiti are implemented in the backend and Effect Studio,
subject to configured category visibility and device capabilities. The initial
H6099 category default is Video; other available categories can be enabled in
the integration's Configure action.

| Workflow | Implemented Bounds and Behaviour |
| --- | --- |
| Basic | Fade `0:(0,1,2)`, Jumping `1:(0,2)`, Blinking `2:(0,1,2)`, Marquee `3:(3,4,5)`, Stream `8:(9,10)`, Flow `9:(9,10)`, Chase `10:(0)`, Music `4:(8,6,7)`. Speed 1-100 except DIY Music, whose wire rate is fixed at 50 and has no speed control. Palette 1-8 colours, or 1-3 for Chase. |
| Mixed | 1-4 family/variation pairs from families 0, 1, 2, 3, 8, 9, with shared speed 1-100 and palette of 1-8 colours. Chase and DIY Music are not Mixed members. |
| Graffiti | Physical-IC addressing, not logical segments. A known count and matching authored array are required; the document representation supports 1-255 ICs. Speed and brightness are 0-100. Background colour is retained, defaulting to white. Clockwise, counter-clockwise, cycle, gradient, twinkle, and breathe motions are available. |

Uploads use exact H6099 framing and ordinary `33 05 0a` activation with a
little-endian DIY code, default **254**. Readback reports only that code, not
the authored content or a unique payload identity. Reusing a code can overwrite
the prior payload; recovery does not claim to restore an overwritten unknown
DIY. A matching selector is not proof of a visible effect.

Advanced authoring, edited catalogue scene payloads, H6199 palette-DIY carriers,
and Workshop remain unavailable. Ordinary Basic/Mixed/Graffiti support does not
authorize those routes or arbitrary app-authored DIY import.

### Onboard Music

Native selectors are Energetic, Rhythm, Spectrum, Rolling, Separation, Hopping,
Piano Keys, Fountain, Day and Night, Bloom, and Shiny. These use the device's
microphone, never phone/host audio. Native selection, Studio application, and
recovery share the ordering **power on, applicable A3 `41` companion upload,
then `33 05 13` selector**. A native selector remains available when physical
IC count is unknown; only dependent companion/parameter writes are blocked.

- Rhythm, Spectrum, Energetic, and Rolling use legacy selector fields, including
  optional fixed colour. Rhythm supports calm/dynamic style. Energetic's
  different new-detail upload path remains unresolved.
- Bloom and Shiny have IC-independent palettes and calm/dynamic companions.
  Separation exposes point 1-5 and gradient; Hopping exposes packed RGB
  background and relative brightness 0-50; Piano Keys exposes IC-derived key
  count bounds and gradient; Fountain exposes clockwise, counterclockwise, and
  two-way direction. These latter companions require physical IC count.
- Day and Night retains the app-derived default companion, requiring IC count.
  Its UI-to-controller indexing is inconsistent, so segment-count, speed, and
  gradient editing are not exposed as qualified parameters.
- New-music status establishes mode and sensitivity, not companion parameters,
  palette, or Bloom/Shiny style. Unknown trailing bytes are not decoded as
  legacy style/colour. Companion writes and retained/recovered settings are
  **not guaranteed readback**; Studio verification is only a mode match for
  companion-bearing requests.
- The backend parameter contract feeds the existing generic parameter editor.
  Qualified modes expose the existing palette editor with 1-8 colours and a
  reset to their APK defaults. Optional palettes survive profile storage,
  application, preview, and recovery without changing older document hashes.
  Interrupted uploads invalidate retained palette knowledge; recovery never
  substitutes defaults for an unknown prior palette. Palette readback is not
  available, so even a replayed known palette remains unverified. Hopping
  background is still a numeric packed-RGB parameter, not full app-UI parity.

### Video

Movie/Game, partial/full capture region, saturation, sound effects with softness,
scalar white balance **1-100** (default 50), four-edge relative brightness, and
blank-screen detection are implemented. White balance is not an H6199 red/blue
pair or a camera image-calibration workflow.

H6099 saturation writes and Studio editing use **1-100**, matching Android
7.6.01's shared saturation UI; Studio templates start at **100**. H6199 retains
its **0-100** range. Received H6099 zero (or another out-of-range value) remains
in the raw protocol evidence but is not accepted as fresh saturation state.
Sibling video fields still update; cached saturation is not promoted to a fresh
observation. Recovery and retained-setting writes must satisfy the target range.

Blank-screen profiles can author detection `1` (low brightness) or `2` (same
tone) and both unsigned 16-bit duration fields in seconds (0-65535). Toggle-only
requests first obtain fresh policy and preserve it; explicit policy writes and
recovery retain the full tuple. Reconnects and intervening policy changes are
guarded at the physical write boundary. Wire bounds are not a claim that every
duration has been physically qualified.

Black-border removal is implemented via `A9 0B`, gated specifically by
**Wi-Fi software** `subordinate_21_version >= 1.00.11`, not BLE firmware or
Wi-Fi hardware. Missing/malformed identity is an evidence gap; older identity
is unsupported. Queries, requested writes, and recovery use this gate, rechecked
after reconnect. Unrequested border settings do not block ordinary video.

### Installation Direction and Camera Health

These are actions on the existing light, not new entities or a calibration UI:

```yaml
action: ha_govee_led_ble.set_installation_direction
target:
  entity_id: light.your_h6099
data:
  value: "2"
```

Only numeric values/labels **2, 3, 4, 5** are accepted. No corner or viewing-side
mapping is claimed. The write does not power on, select video, enter calibration
display, or change camera position. It requires fresh matching direction
readback, installs no optimistic direction, and fails without confirmation.
Failure does not undo a write that reached the device.

```yaml
action: ha_govee_led_ble.read_installation_controls
target:
  entity_id: light.your_h6099
response_variable: installation
```

The response contains `installation_direction` (2-5 or null) and `camera_health`
(`absent`/0, `healthy`/1, `incompatible`/2, or `unknown`). Missing or unrecognized
replies are unknown, never absent/healthy. Each domain requires its own fresh
revision, so a partial response does not reuse the other domain's cached value.
Both queries run on refresh; missing optional replies do not gate setup or
disconnect an otherwise usable light solely for these domains. Disconnect
clears their observations. Camera position `31` is neither read nor written.

### DreamView

The MovieFeastV2 candidate is **service-only**, with at most **seven members**.
There is no DreamView Studio editor, discovery wizard, or new state entity.
The [action schemas](../custom_components/ha_govee_led_ble/services.yaml) and
[service registry](../custom_components/ha_govee_led_ble/dreamview_services.py)
define `replace_dreamview_group`, `delete_dreamview_group`,
`read_dreamview_group`, and setters for switch, member brightness/connection,
same brightness, saturation, sample, and sound effects.

- Replacement is explicit, not a merge. Each member requires externally known
  `cmd_ver`, `is_rgbic`, exactly one MAC address or UTF-8 BLE name, and explicit
  areas. No command-version default or metadata discovery is supplied.
- Area values are wire 1-10, 0 unassigned, or 255 disabled. Empty area lists and
  disabling a single-area member are blocked because the APK path is not
  established. Member control indices are 0-6; brightness/saturation/softness
  are 0-100. Both sample bytes are explicit 0-255 values without inferred labels.
- Replacement/deletion intent is atomically saved before transmission in the
  private config-entry Store `ha_govee_led_ble.dreamview.<entry_id>`. Save failure
  prevents transmission. Unload/reload retains locally authored metadata;
  deletion retains the last authored member list for explicit manual recovery.
- Authored data is **local request data, never confirmed membership**. Failure
  or cancellation can leave a partial device group. Write status is only
  `not_attempted`, `attempted_unconfirmed`, or `sent_unconfirmed`; a new process
  starts at `unknown`. Neither an ACK nor successful transmission proves success.
- Read responses separate `authored` from `observed`, always report
  `membership_confirmed: false`, and mark membership readback unavailable and
  slot identities unknown. They preserve ten anonymous connection bytes and all
  sixteen brightness bytes, including zeros and unknown tails. These do not
  establish member count, identity, absence, or successful deletion.
- Only individual replies received during the read window are returned; missing
  settings stay missing. There are no transaction IDs, so even a reply received
  after dispatch does not prove causal freshness or confirm a preceding write.
- Membership uploads redact packet/debug raw data for the transaction, including
  reconnect/retry handling. Private authored identities are not exported in
  diagnostics. The read action returns those identities to its authorized caller;
  do not share that response unredacted.

No digest `0x0c`, active member identification, candidate scanning, camera
heuristic, automatic group restoration, cloud access, calibration, or streaming
control is implemented. Existing app-authored membership cannot be read or
recovered before replacement. Private Store cleanup on permanent config-entry
removal is not implemented; ordinary unload deliberately preserves it.

### Encryption and Exclusions

The connection session selects encryption from a discovered encryption
characteristic and/or positive advertisement evidence, not merely the SKU.
Negotiation precedes identity/control traffic. Failure, malformed markers,
authentication rejection, or a previously established encryption requirement
does not authorize plaintext fallback. Notifications are decrypted before
logical protocol routing; session keys/IVs are cleared on reset and omitted
from diagnostics.

- **V1:** two-phase handshake and the vendor AES-ECB/full-block plus RC4/tail
  transform are implemented. This is unauthenticated vendor encryption, not
  modern secure messaging; logical reply checksum validation still applies.
- **V2 subset:** AES-GCM uses only **16-byte tags**, with counters and replay
  rejection. Negotiation requires negotiated **ATT MTU >= 53** so its 50-byte
  reply fits. The BlueZ backend can acquire the actual MTU; each data frame must
  also fit `MTU - 3`. Short-MTU `E7 19` / `E7 1A` fragmentation and other tag
  lengths are unsupported and fail closed. Ordinary bounded A3 effect chunks
  are not a substitute for encrypted-handshake fragmentation.

These implementations do not prove which version an owner's H6099 requires or
qualify every Home Assistant Bluetooth adapter/proxy path.

Under the [global scope policy](scope-policy.md), AI filters, provisioning/cloud
device communication, onboard schedules, host audio/continuous streaming, OTA,
and cloud camera image calibration remain excluded. Known Wi-Fi/timer payloads
are documentation-only. Provisioning/cloud exchanges are not currently
decryptable into a usable, qualified workflow with this integration's evidence
and implementation; this is a present limitation, **not** a claim that decryption
is inherently impossible. Local BLE V1/V2 support does not establish that workflow.

## Model-Specific Changes and Owner Checks

The implemented model-specific path spans the
[profile](../custom_components/ha_govee_led_ble/const.py),
[effect catalogue](../custom_components/ha_govee_led_ble/effect_catalogue.py),
[compiler](../custom_components/ha_govee_led_ble/effect_compiler.py),
[music semantics](../custom_components/ha_govee_led_ble/music_semantics.py),
[coordinator](../custom_components/ha_govee_led_ble/coordinator.py),
[installation helpers](../custom_components/ha_govee_led_ble/h6099_controls.py),
[DreamView mixin](../custom_components/ha_govee_led_ble/coordinator_dreamview.py),
and [encryption session](../custom_components/ha_govee_led_ble/govee_encryption/session.py).
Coordinator composition, notification routing, optional control queries,
physical-IC propagation, and DreamView privacy hooks are integrated in that path.

Repository checks cover structure and software behaviour, not hardware:

| Existing Check | Coverage |
| --- | --- |
| [test_h6099.py](../tests/test_h6099.py) | Exact profile, logical command/status bytes, all 240 scene paths, declared read domains, segment pages. |
| [test_h6099_diy.py](../tests/test_h6099_diy.py), [browser DIY checks](../frontend/tests/browser/h6099-diy.spec.ts) | Basic/Mixed bounds, activation, physical Graffiti, background preservation, desktop/mobile IC controls. |
| [test_h6099_music.py](../tests/test_h6099_music.py) | IC-derived parameters, palette builder, order/state boundaries for native, Studio, and recovery routes. |
| [test_h6099_video.py](../tests/test_h6099_video.py), [test_h6099_coordinator.py](../tests/test_h6099_coordinator.py) | Wi-Fi identity gating, policy preservation/recovery, exact fresh observations, geometry/reconnect guards. |
| [test_h6099_controls.py](../tests/test_h6099_controls.py) | Registered actions, concrete coordinator refresh, optional/partial replies, direction confirmation and stale-state rejection. |
| [test_h6099_dreamview.py](../tests/test_h6099_dreamview.py) | Seven-member validation, anonymous reads, private persistence, retries/cancellation, concrete encrypted notification routing and raw-log redaction. |
| [test_govee_encryption.py](../tests/test_govee_encryption.py) | Crypto/session software checks and fail-closed transport boundaries. |

Remaining explicit gaps against the broad candidate scope are:

- Owner qualification of connection/encryption, basic controls, all exposed
  effect families, visible activation, readback, and restoration. Test fixtures
  do not promote the model beyond Experimental.
- App-equivalent parameter presentation, Energetic's new-detail companion,
  and Day/Night editable parameter semantics;
  actual companion acceptance/readback remains unproven.
- Physical qualification of video saturation and border removal on the reported
  Wi-Fi version.
- Physical IC topology and numeric installation-direction orientation labels;
  camera position is separate and unimplemented. Time sync is not proven to be
  needed for in-scope control and is not implemented.
- Advanced/edited-scene/Workshop application, complete V2 fragmentation/tag
  coverage, and DreamView membership readback/identification/restoration are not
  implemented. DreamView remains local-authored, service-only, and unconfirmed.

Use the [owner validation process](../CONTRIBUTING.md#device-owner-validation)
for an exact-SHA model prerelease: first ask the owner to try available features
and supply immediate redacted diagnostics after failures. Follow up only where
results need clarification. Record exact firmware/Wi-Fi versions, observed versus
optimistic state, and restoration results. Do not replace a DreamView group
unless its owner accepts that previous membership cannot be recovered here.
Promotion follows the contributor lifecycle, not a passing software test count.
