# H6199 support findings

Investigation and verification ledger for
[#294](https://github.com/teh-hippo/ha-govee-led-ble/issues/294), which blocks #293.
Evidence collected 2026-09-16 against integration commit `8db855e` and Govee
Android 7.6.01. Baseline release comparison: v7.5.2 / `6ded467`.
The numbered findings below describe that baseline; the implementation
dispositions at the end distinguish fixes from remaining qualification gaps.

## Scope and evidence

The tested H6199 has main HW `3.02.01`, main FW `1.10.04`, Wi-Fi HW
`1.03.00`, and Wi-Fi FW `1.00.33`. Direct advertising data independently
identifies Pact `2/1`, broadcast version 2, without the encryption flag.
It is not the HW `1.00.01` / FW `1.07.02` device in issue #293.

Direct tests used the attached CSR dongle (`hci0`) through host BlueZ, with
only this device's Home Assistant config entry disabled. No firmware,
provisioning, camera image calibration, group membership, or effect upload
was changed. Settings/mode writes had an explicit restoration sequence.
The light was initially off; these tests establish register acceptance and
readback, not visual output or microphone/camera performance.

After testing, all 19 baseline queries returned byte-identical responses:
power, four identity versions, brightness, both mode-query variants, white
balance, blank-screen policy, edge brightness, direction, camera position,
camera health, gradual state, and four segment pages. HA ownership was
restored and the entry loaded with `light.dream_tv` off. This comparison
does not establish equality of inaccessible inactive-mode/device memory.

Evidence levels used below:

- **Device + code:** direct fresh status reply and demonstrated integration mismatch.
- **Software:** reproducible implementation behavior, not induced on production hardware.
- **APK:** reachable app behavior; not fully qualified on the physical device.
- **Unconfirmed:** hypothesis or qualification gap, not a reproduced defect.

APK paths below are relative to
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources/`.

## Confirmed problems

### 1. White-balance mode is lost during state capture and restoration

**Device + code; present in baseline and prerelease.**

With current red/blue held at `(21, 5)`, the device accepted both flag values:

```text
Automatic-labelled state: aaa9000601100300150500000000000000000007
Manual-labelled state:    aaa9000601100301150500000000000000000006
```

The APK interprets that flag and preserves it when writing normal white
balance. The integration's recovery snapshots are identical for these two
real replies, and rewriting the captured white balance always emits flag 1.
Returning to the same red/blue values therefore does not restore the whole
white-balance state. This is not a claim that automatic camera adjustment
was visually tested.

The reply also contains device-reported reset flag/red/blue values, which
the integration discards. The tested reset tuple is `(1, 16, 3)`, matching
our current fixed reset; differing device defaults were not physically found.

Sources: `custom_components/ha_govee_led_ble/coordinator.py:1241-1252`,
`generated_protocol_adapter.py:1030-1058`,
APK `com/govee/pact_tvlightv2/newdetail/VM4Light.java:698-713` and
`com/govee/base2light/videomode/newdetail/funtion/WhiteBalanceVmInterface.java:77-79`.

### 2. Spectrum and Rolling fixed-colour controls disappear in the prerelease

**Device + code; regression from baseline.**

The catalogue advertises `colour: false` for both modes, causing the editor
to hide their fixed-colour control. The backend still accepts those values.
Direct writes produced these matching mode/status replies:

```text
Spectrum, RGB 32/96/160: aa0513040000012060a000000000000000000059
Rolling, RGB 160/96/32:  aa051306630001a0602000000000000000000038
```

The APK exposes fixed colour for these modes. This proves accepted state,
not the appearance of the music effect while the light is off.

Sources: `custom_components/ha_govee_led_ble/effect_catalogue.py:231-239`,
`const.py:509-513`, `music_commands.py:93-102`,
`frontend/src/music-profile-editor.ts:91-128`,
APK `com/govee/pact_tvlightv2/newdetail/OldMusicMode.java`.

### 3. Valid sensitivity zero cannot be reapplied

**Device + code; present in baseline and prerelease.**

The device accepted Spectrum sensitivity 0 and returned the Spectrum frame
above. Feeding that actual frame to the coordinator retains sensitivity 0,
but reselecting Spectrum raises `music sensitivity is outside model limits`
before any write. Our permitted range starts at 1; the app permits 0.

The device also accepted and reported sensitivity 100:
`aa0513046400012060a00000000000000000003d`. Therefore the earlier suggestion
that 100 is unsupported is withdrawn. The APK UI's 0-99 ceiling and the
device's acceptance of 100 are separate facts.

Sources: `custom_components/ha_govee_led_ble/const.py:511-512`,
`coordinator_modes.py:229-277`,
APK `com/govee/pact_tvlightv2/newdetail/Info4Detail.java:280-295`.

### 4. Ordinary DIY selection is reported as unknown/colour

**Device + code; present in baseline and prerelease.**

Sending `33 05 0A FE 00 00 00` selected code 254 without uploading content.
Both mode-query variants returned:

```text
aa050afe0000000000000000000000000000005b
```

The H6199 parser does not name selector `0x0a`; it produces UNKNOWN with no
DIY code. With the coordinator on, its coarse active-mode fallback reports
colour. The physical test establishes selector/readback support, not that
slot 254 contained a valid effect or that arbitrary DIY playback succeeds.

Sources: `tools/ble/kaitai/h6199_status_reply.ksy:53-57`,
`custom_components/ha_govee_led_ble/coordinator_modes.py:77-88`,
APK `com/govee/base2light/effectPlay/effect/mode/SubModeNewDiy.java:79-106`.

### 5. Gradient setting is absent and its readback is discarded

**Device + code; present in baseline and prerelease.**

`33 A3 01` and `33 A3 00` changed the setting, confirmed by `AA A3` replies.
In static mode, enabling it also changed mode readback to:

```text
aa051501000000000000000000000000000000bb
```

The app labels this **Color > Subsection > Gradient**. The baseline semantic
parser and recovery state do not expose that gradual byte.
There is no corresponding H6199 setting in the integration. Our previous
H617A-specific rationale for excluding gradual control does not establish
an H6199 limitation. This is a persistent device setting, not proof of
support for arbitrary HA transition durations.

Sources: `tools/ble/kaitai/h6199_status_reply.ksy:141-154`,
`custom_components/ha_govee_led_ble/coordinator_status.py:103-122`,
APK `com/govee/base2light/pact/newdetail/content/colorv2/DelegateColorV2Part.java:462-496,636-643`,
APK `com/govee/base2light/pact/newdetail/config/fuc/color/Bytes.java:563-565`.

### 6. Installation controls and camera-health observations are absent

**Device + code; present in baseline and prerelease.**

- Direction: `33 30 01` changed `AA 30` from 0 to 1; restored to 0.
- Camera position: `33 31 01` changed `AA 31` from 0 to 1; restored to 0.
- Camera health: `AA 32` returned `aa32010000000000000000000000000000000099`.

The app maps the two installation values to clockwise/anticlockwise and
top/bottom, and interprets camera status. The integration does not expose
these H6199 controls/observations. Only the attached healthy camera was
tested; absent/incompatible camera states and visual orientation were not.

Sources: `custom_components/ha_govee_led_ble/const.py:464-508`,
APK `com/govee/pact_tvlightv2/add/CameraSettingsAc.java:164-186,265-293,374-429`,
`com/govee/pact_tvlightv2/newdetail/VM4Light.java:643-655,692-695`.

### 7. Partial segment-write failure restores stale observation authority

**Software; present in baseline and prerelease.**

A reproduction starts with observed segment state, allows the first colour
group send to succeed, then raises `BleakError` on the second. The coordinator
restores all old colours, their old observation timestamp, and `observed`
provenance, without querying the potentially partly changed device.

This is a deterministic error-path reproduction, not a claimed physical
disconnect observed during these tests. Separately, segment operations
discard the Boolean result of their final verification refresh.

Source: `custom_components/ha_govee_led_ble/coordinator.py:2173-2227`.

## Additional capability differences

### 8. H6199 multi-device DreamView is not exposed

**APK + read-only device evidence; full control unqualified.**

The app's revision checks enable DreamView iteration 1 for this unit. Its
reachable H6199 implementation differs from the H6099 MovieFeastV2 path.
The device answered the legacy enable query `AA 54` with disabled state:
`aa540000000000000000000000000000000000fe`.

The integration rejects the H6199 profile for DreamView services. No group
membership, enable state, member controls, capacity limit or synchronization
was modified/tested. A response to `AA 54` does not qualify membership uploads.

Sources: `custom_components/ha_govee_led_ble/dreamview.py:22-30`,
APK `com/govee/home/main/device/moment/Constant.java:227-243,593-611`,
`com/govee/home/main/device/moment/moviefeast/ble/Ble.java`.

### 9. Basic/Mixed DIY editor coverage is incomplete

**APK; upload/playback differences not physically qualified.**

The integration exposes nine H6199 palette family/variant combinations;
the reachable APK Basic DIY roster has nineteen, plus Mixed DIY. Missing
combinations include Fade 1/2, Jumping 2, Blinking 1/2, Marquee 4/5,
Stream/Flow 10, and Music DIY 6/7. The current palette route uses a different,
capture-backed activation carrier. These facts do not prove that the
existing carrier is broken or that every additional payload is safe.

No effect upload was attempted: existing device-resident content cannot be
backed up through HA. Selector support was independently tested in item 4.
Speed/colour-count bounds also differ from the app; their physical limits
remain unqualified.

Sources: `custom_components/ha_govee_led_ble/effect_catalogue.py:443-575`,
`effect_compiler.py:596-635`,
APK `com/govee/pact_tvlightv2/newdetail/diy/H6199DiyConfig.java:52-148`.

### 10. Selected-segment temperature-based colour choice is not exposed

**APK + device; native Kelvin persistence not established.**

The app offers temperature-based colour selection for selected segments.
A masked 6500 K command changed only the selected segment's rendered RGB
from the preceding 3000 K colour; other segments retained their prior RGB.
Our segment services offer RGB/brightness, not a temperature-based choice.

Readback demonstrates rendered RGB, not persistent per-segment Kelvin.
Since equivalent RGB painting is available, this is a narrower authoring
capability gap, not proof that the light needs a new native temperature mode.

Sources: `custom_components/ha_govee_led_ble/light_services.py:47-104`,
APK `com/govee/pact_tvlightv2/newdetail/ColorMode.java:302-327`.

## Qualification and modeling limitations

### 11. Model-level support does not express H6199 revision differences

**APK + code; old-hardware failure not reproduced here.**

The app gates features using main HW/FW, Wi-Fi HW/FW, and advertised Pact.
Our H6199 profile enables the newer video registers and requires their
readback during setup independent of those identities. This device passes
the app's gates; issue #293's hardware does not. Both tested integration
versions successfully removed/re-added this newer device.

Although our advertisement parser extracts Pact, the coordinator only uses
its encryption indication; it does not retain Pact for H6199 diagnostics or
protocol decisions. Direct evidence now establishes this unit's Pact 2/1.

Sources: `custom_components/ha_govee_led_ble/const.py:464-508`,
`advertisement.py:9-30`, `coordinator.py:662-668`,
APK `com/govee/pact_tvlightv2/pact/Support.java:331-402`.

### 12. DreamView compatibility, capacity and capability are conflated

**Code/design limitation; not an existing H6199 wire-level failure.**

`command_grammar == "H6099"` is a wire-family selector, not literally a SKU
check; grammar selection is necessary for incompatible encodings. However,
DreamView writes also require capacity exactly seven, and use the ordinary
command grammar as an indirect DreamView compatibility indicator. Receive
routing accepts any positive capacity with H6099 status grammar. Capacity
alone does not establish protocol compatibility, and a generic enabled flag
alone would not make H6199 safe to route through these fixed serializers.

Sources: `custom_components/ha_govee_led_ble/dreamview.py:22-30,149-190`,
`coordinator_dreamview.py:66-75`, `dreamview_services.py:34-91`.

Resolved in #306 for compatible consumers: explicit `dreamview_grammar`,
independent write/read declarations, and target-specific capacity replace
these indirect guards. Capacity gates only replacement and indexed writes;
basic grammar restrictions do not authorize or block DreamView transactions.
Synthetic exact-profile tests cover partial reads, notifications, physical
authorization and reduced capabilities after preparation. This does not
qualify another product or implement H6199's incompatible legacy protocol.

### 13. Transport completion and operation-deadline gaps

**Code/APK difference; physical failure not reproduced.**

The app advances ordinary controller operations on matching replies and
multi-packet progression on completion callbacks/device results. Our
integration logs command ACKs without using them as transaction completion;
some paths rely on later state verification and some remain optimistic.
Direct tests confirm ACKs exist, but did not induce a negative ACK or an
upload failure. No conclusion about upload pacing is physically qualified.

Two fresh-session burst-query runs and two reply-paced runs each received
all ten queried responses without retry on the local dongle. Therefore
"burst writes cause dropped replies" is not a reproduced finding here.
Earlier proxy-based setup tests needed the built-in retry, but they are not
a controlled adapter/timing comparison.

The integration's refresh deadline does not bound each underlying GATT
write; a stuck operation can exceed that budget. Dependency timeouts and
practical failure frequency were not fault-injected on the production radio.

Sources: `custom_components/ha_govee_led_ble/coordinator.py:1154-1177,1343-1387,1723-1795,1901-1966`,
APK `com/govee/base2light/ble/comm/ComposeBleComm.java:209-324`.

## Claims withdrawn or narrowed

- **Kelvin readback:** neither `AA 05 00` nor `AA 05 01` returned Kelvin
  after a successful 3000 K write; both returned static detail zeroes.
  Rendered segment RGB changed correctly. The APK parser alone does not
  establish that our integration is discarding a real Kelvin value here.
- **Mode query discriminator:** both variants returned identical video,
  static-colour and DIY selector data in these tests. No functional defect
  from our zero discriminator was demonstrated.
- **Sensitivity 100:** physically accepted/read back. The confirmed issue
  is rejecting zero, not accepting 100.
- **Video saturation zero:** the original and restored device state reports
  zero. The app's narrower UI range alone does not prove zero invalid.
- **White-balance reset:** this unit's reported default matches our fixed
  reset tuple. Losing the field is established; a wrong default on this
  unit is not.
- **Blank-screen policy:** disabled-policy mode/durations were changed,
  read back, restored and verified. The prerelease already supports these
  fields; it is not a missing H6199 capability. Extreme duration bounds and
  actual blank-screen detection behavior were not tested.
- **Init/keepalive:** all direct sessions worked without `AA 14` or time
  sync. No old-hardware watchdog claim was tested or confirmed.
- **Topology:** 15 ordinary segments, four video edges and four native music
  modes remain appropriate; H6099's extra modes/topology must not be assumed.

## Evidence locations and checks

Private/local raw captures (not intended for uploading wholesale):

- `/tmp/opencode/h6199-baseline.jsonl`
- `/tmp/opencode/h6199-settings.jsonl`
- `/tmp/opencode/h6199-modes.jsonl`
- `/tmp/opencode/h6199-diy-selector.jsonl`
- `/tmp/opencode/h6199-query-timing.jsonl`
- `/tmp/opencode/h6199-restored.jsonl`
- `/tmp/opencode/ha-293-direct-before.json`
- `/tmp/opencode/ha-293-direct-enabled.json`

Temporary runnable reproductions:
`/tmp/opencode/issue-293-proof/tests/test_h6199_claims_proof.py`.
Seven checks pass by asserting the problematic current behavior, including
replay of actual captured WB, sensitivity-zero and DIY frames. Another 155
focused existing tests passed before capture replay. These are not fixes.

```bash
# Run from /tmp/opencode/issue-293-proof:
/tmp/opencode/issue-293-main/.venv/bin/python -m pytest -q tests/test_h6199_claims_proof.py

# All 19 baseline query replies must occur twice and match:
jq -s -e 'map(select(.kind == "matched")) | group_by(.step) | all(.[]; length == 2 and .[0].raw == .[1].raw)' /tmp/opencode/h6199-baseline.jsonl /tmp/opencode/h6199-restored.jsonl
```

Full DIY uploads, DreamView membership, absent-camera behavior, visual effect
output, sustained throughput, and the older revision remain unqualified.

## Implementation Disposition

### Active Scope For #293

The target is **H6199 HW 1.00.01 / FW 1.07.02**, not H6099 and not the
newer Dream TV used for the physical tests above.

Commit `a0bfec0` removes the demonstrated software setup obstacle: only power,
brightness and colour/mode replies are mandatory. Revision-gated white balance,
relative brightness and blank-screen queries are omitted for the reporter's
versions. Missing Wi-Fi identity does not prevent basic setup. The exact-version
fake-radio regression is
`test_issue_293_setup_requires_only_basic_readback`; it also checks that missing
basic replies still fail rather than loading optimistically.

Retired from the active investigation: WB state loss, hidden Spectrum/Rolling
colour controls, rejection of sensitivity zero, misclassified DIY readback and
stale segment rollback. Their fixes and qualification limits remain recorded
below. Expanded DIY, legacy DreamView and cloud firmware checks are separate
work, not prerequisites for resolving this setup failure.

Remaining gate: an owner test on the older hardware with an exact candidate
build. If setup still fails, identify missing/rejected basic replies and the
actual GATT characteristics from that attempt. Pact 1 differs in brightness,
colour, music and segment formats, not just segment readback. Positively
identified Pact 1/1 therefore selects the [power-only profile](h6199-pact1.md);
the reporter's hardware version alone does not select it. The exact-version
test above uses synthetic percentage/static-mode replies and establishes setup
policy, not qualification of the older wire formats. The claimed `AA 14`
handshake, three-second watchdog and need for a longer timeout remain hypotheses.

### Independent RC Review

The reporter candidate builds on `v7.6.0-rc.2.h6199` (`a0bfec0`). Independent
runtime, consumer/applicability and Kaitai reviews found and corrected:

- Optional-query write failures rejecting successful basic setup/keepalive;
  required errors and actual disconnects still fail. Successfully sent optional
  replies are collected within the existing deadline, including video registers.
- Unrelated white-balance recovery blocking power restoration after non-video
  deployments. New non-video snapshots have an explicit empty video scope.
- Historical segment observations incorrectly constraining untouched siblings;
  only transaction-fresh sibling observations are preservation expectations.
- Stale static-mode Gradient falsely confirming an independent register write.
  Independent confirmation now requires its own register observation.
- Qualification evaluated during background reconnect, before admission; stale
  saved/default video choices; and missing publication of Pact changes.
- Known Pact 1 accepting incompatible Pact 2 operations. The effective profile
  now governs entities, selectors, compilation and the physical write boundary.
  Profile changes invalidate in-flight controls and bound read-batch retries.
- Lossy Kaitai command/display extensions and video-reply tails, missing H6099
  direction ACK classification, unsupported music selector state mutation, and
  recovery storage rejecting a decoded zero-valued relative-brightness setting.

Regression coverage is in `test_query_isolation.py`, `test_revision_consumers.py`,
`test_reconnect_admission.py`, `test_gradient_observations.py`,
`test_h6199_pact1.py`, `test_profile_transitions.py`, and
`test_protocol_review_regressions.py`. Final `make check` passed: 2,243 Python
tests passed, 79 skipped, plus frontend unit/browser checks, lint, type checking,
and generated-code verification. No physical-device test was performed for these
review corrections. General upload ACK sequencing and hardware qualification
remain separate from these confirmed fixes.

Software checks below run through `make check`. They do not supersede the
official-app capture and owner-qualification requirements in CONTRIBUTING.md.
No installed integration or physical device has been changed during this
implementation. The issue remains open until its outstanding items are resolved
or explicitly excluded; publishing a candidate does not close it.

| Finding | Candidate disposition | Runnable coverage / remaining gate |
| --- | --- | --- |
| 1. WB flag/defaults | Preserve six fields; manual authoring is explicit, recovery retains the captured flag, reset reads device defaults; legacy missing flags remain unknown | `tests/test_h6199_white_balance.py`; installed-RC recovery and restoration still required. See [field contract](h6199-white-balance.md). |
| 2. Spectrum/Rolling colour | Explicit native music metadata agrees with backend and editor; Energetic remains without fixed colour | `tests/test_h6199_capabilities.py`, frontend contract fixture; visible music/microphone qualification pending. |
| 3. Sensitivity zero | Qualified range 0..100 | Boundary and mode checks in `tests/test_h6199_capabilities.py` and existing coordinator tests. Device acceptance predates candidate, HA control/readback still pending. |
| 4. DIY selector | Decode ordinary DIY code instead of UNKNOWN; command layout documented, no unused runtime builder or new activation authorization | `tests/test_kaitai_protocol.py`, `tests/test_h6199_native_controls.py`; resident playback and automatic restore remain unqualified. |
| 5. Gradient | Opt-in native select and independent register readback; static detail decoded | `tests/test_h6199_native_controls.py`; visual effect and any implied mode-side effects need installed-RC testing. Not arbitrary transition timing. |
| 6. Installation/camera | Disabled-by-default camera-position/direction selects; diagnostic unknown is distinct from absent/incompatible | Native-control and capability tests cover late identity, polling/disconnect, timeout, mismatched replies and write guards. Only exact captured revision authorized; physical orientation and faulty/disconnected camera remain unqualified. See [register contract](h6199-native-controls.md). |
| 7. Segment failure | Write-boundary optimism, bounded reconciliation without masking original errors, no stale rollback; complete readback must match requested values and observed untouched siblings | `tests/test_coordinator.py`, including partial groups, unchanged replies, cancellation and other-model cases; live successful grouped writes/restoration pending, no induced radio failure authorized. |
| 8. Legacy DreamView | Deferred, not routed into H6099 MovieFeastV2; no membership mutation | Existing `tests/test_h6099_dreamview.py` and H6199 capability gate. Requires legacy protocol/capacity evidence and separately approved restorable membership test. HA backup is insufficient. |
| 9. Basic/Mixed DIY | Additional combinations/uploads remain unavailable; existing capture-backed catalogue unchanged | Existing effect catalogue/compiler tests; requires complete payload/activation qualification and separately approved restoration source for resident content. |
| 10. Segment temperature authoring | Deferred authoring convenience; existing RGB painting retained; no native Kelvin persistence claim | Existing segment builder/service tests retain RGB/brightness contract. Needs explicit temperature-input contract and generated masked writer/readback tests before exposure. |
| 11. Revision/Pact | Retain Pact in diagnostics; effective APK revision gates apply to queries, writes and recovery; optional newer silence cannot fail basic setup | `tests/test_h6199_capabilities.py`: older/unknown identity, missing basic replies, delayed fresh requalification, H6099 regression. Physical older HW remains unavailable. |
| 12. DreamView protocol/capacity | Resolved for compatible consumers in #306 via explicit codec, operation/read subsets and product capacity; no second wire family required | `tests/test_dreamview_profiles.py` proves independent basic grammars, partial reads and physical authorization; `tests/test_h6099_dreamview.py` preserves exact bytes and membership uncertainty. H6199 legacy DreamView remains deferred. |
| 13. ACK/deadlines | New native writes require fresh register replies, not ACKs. Identity reply waiting and segment reconciliation are bounded. No blanket pacing/ACK transaction rewrite | Native-control tests reject ACK-only/missing confirmation; existing sequence tests cover retries. Underlying general refresh GATT writes still depend on transport/caller timeouts; negative upload ACKs and hung production radio remain unqualified. |

The narrowed/withdrawn claims above remain withdrawn. No query-discriminator,
keepalive, saturation, topology or existing blank-policy rewrite was made.

## Issue #115 live A3 response rejection (2026-09-17)

H6199 HW `3.02.01` / FW `1.10.04` produced three identical checksum-valid
notifications during the palette DIY workflows:
`a3040000000000000000000000000000000000a7`. The private integration diagnostics
reported each as `schema_rejected` by `h6199_status_reply`: the command-ACK root
accepted only header `33`, so A3 fell through to the status parser. These are
integration notifications, not official-app captures; the private export is not
repository evidence. Successful workflow readback is independent of these ACKs.

APK response trace (Android 7.6.01, paths relative to `com/govee/`):

- `pact_tvlightv2/iot/OpDiyCommDialog4BleIot.java:32-40,85-100` selects
  `MultipleDiyControllerV1`, checks its upload result, then separately selects a mode.
- `base2light/ble/controller/MultipleDiyControllerV1.java:6,15-18` declares
  command `04`; `AbsMultipleControllerV14Diy.java:6,39-42` forwards the result.
- `base2light/ble/controller/AbsMultipleControllerV1.java:18-35,52-54` declares
  protocol A3 and tests absolute byte 2 for zero success.
- `base2light/ble/controller/AbsController.java:97-99` matches protocol and
  command, providing no effect identity or transaction correlation.

The exact H6199 speculative upload-ACK payload names only opcode/status and
preserves the sixteen unknown trailing bytes. The existing notification ACK
path records it without changing observed state or confirming activation.
`tests/test_kaitai_protocol.py` replays the literal notification and checks
negative statuses, unknown-tail round trips, malformed frames and unrelated
opcodes. Negative statuses/nonzero tails are synthetic APK-contract tests;
physical negative replies, other upload commands/revisions and general H6199
upload-ACK sequencing remain unqualified. No new upload policy is enabled.

## Release And Restoration Gates

Independent correctness and separate Ponytail ultra reviews passed after
fixing delayed reconnect qualification, loss of successful polling observations,
and complete-but-incorrect segment confirmation. Final `make check` and an
unused immutable exact-SHA RC are required before delivery.

Before HACS download/install or HA restart, obtain explicit approval of that
specific RC. Then take a fresh verified backup and capture the installed build
and complete restorable device state. Exercise normal HA workflows plus fresh
independent BLE readbacks, restore all captured settings, and verify restoration.
Report optimistic state, register acceptance and visual qualification separately.
No DIY uploads, DreamView membership mutations, camera disconnection, firmware
changes or cloud calibration are authorized by ordinary candidate installation.
