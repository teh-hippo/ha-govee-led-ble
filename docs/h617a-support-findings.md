# H617A support review and direct-device evidence

Reviewed **2026-09-16**, branch `H617A`, starting at **v7.6.0**,
`7783f1dd7beeebc189313fdaf6ee3112812efe1b`. The original findings below describe
that baseline; applicable proof cases have since become corrected-behavior
regressions. Historical repository references are relative to that commit. `CC/` means
`custom_components/ha_govee_led_ble/`; `KSY/` means `tools/ble/kaitai/`.

## Implementation and qualification status — 2026-09-17

The candidate is rebased onto **v7.6.2**,
`488655d9e85b1cbcb36bc17147be458259e0de2e`, including the completed #249
GATT-cache and idle-polling fixes.

| Scope | Software status | Installed-RC qualification |
| --- | --- | --- |
| R1/R2 | Fresh pre-write power, mode, master brightness and static segments; persisted complete layout; faithful on/off restoration and fresh verification | Pending |
| R3/R4 | Mixed segments invalidate incompatible Kelvin; physical-attempt rollback preserves fresh observations and reconciles ambiguous writes | Pending |
| R5/R6 | Exact-mode fixed-colour permissions, mode/sensitivity-only new replies, complete known-body retention/replay and explicit uncertainty for unreadable settings | Pending |
| Music controls | Seven palettes, Piano gradient and Hopping background/no-colour; field-specific physical-IC gates | Experimental; rendering and sound pending |
| Native DIY | Templates 501–507 retain their own identity and use subtype 02 upload, positive result, then their own selector | Experimental; rendering pending |
| Segment Kelvin / light count | Whole-layout preservation checked; AA0F is optional passive diagnostic evidence, never physical geometry | Exact service / broader count interpretation pending |

Correctness and APK/Kaitai reviews found six issues; all were fixed and their
affected flows independently re-reviewed. A fresh Ponytail review supplied five
simplifications, all applied. Final `make check` passed: **2,760 Python tests,
79 skipped, 269 frontend unit tests, 33 browser tests and 132 protocol replays**;
coverage **89.56%**, with strict typing, lint, formatting and generated-output
checks passing.

New ACK, generalized music-tail and AA0F coverage is explicitly owned by
`KSY/speculative/h617a_command_ack.ksy` and
`KSY/speculative/h617a_control_payload.ksy`. APK evidence is not an official-app
capture or a rendering qualification. A delayed same-subtype ACK can remain
indistinguishable from the current upload's result because the wire has no
transaction ID. Unknown physical IC count still gates only dependent controls.

The owner authorised automated qualification of **cupboard skirt only** and
replacement of unreadable resident music/DIY customisations with a known test
baseline. Human animation and sound checks await a later testing window.
**Every Home Assistant restart requires fresh owner approval.** Stable publication
remains gated on the outstanding qualification. Detailed implementation evidence is in
[music](h617a-music-implementation.md) and [native DIY](h617a-diy-implementation.md).

### RC1 installed results and RC2 timing correction

Published `v7.7.0-rc.1.h617a` at
`3d8cdd871a175a38b9dad11757108b717f01aecb`, with package SHA-256
`9b1dba98c4f491c342ed139bf646c302638123e5e89d13a8193aab1cd8d8358e`.
Check, Hassfest and HACS passed. Installation used HACS and an individually
approved HA restart; diagnostics confirmed running `7.7.0rc1` on HA 2026.9.2.

- **Passed:** power, hidden static state, master brightness, whole-strip RGB and
  Kelvin 2000/3000/9000, verified through fresh complete segment replies.
- **Partial:** mixed RGB and relative brightness across all 15 segments, master
  brightness preserving that layout, and zero relative brightness on segments
  1/15 passed. Setting segments 2/7/14 to 100% returned a confirmation failure.
- **Root-cause evidence:** an earlier background poll still had replies in flight
  when the write and its verification queries began. Its old complete segment
  values satisfied the revision gate prematurely. Later readback contained the
  exact requested brightness, before any brightness retry/reset; RGB was unchanged.
  Packet-to-query attribution is inferred because the wire has no query IDs.
- **Cleanup passed:** authorised known warm RGB baseline, master 5%, all relative
  levels 100%, power off. Music, native DIY and remaining checks were not run.
  Raw household diagnostics remain private.

RC2 collects segment replies under the existing control arbiter for all query
producers. Transmission and collection share one absolute deadline; abandoned
batches require a renewed subscription before another control write. Cancellation
cleanup is bounded too. Healthy completion is response-driven, with no settling
sleep or extra reconnect. Indistinguishable unsolicited duplicate batches remain
a wire limitation.

The final RC2 `make check` passed **2,798 Python tests (79 skipped), 269 frontend
unit tests, 33 browser tests and 132 protocol replays**, plus typing, lint,
formatting and generated-output checks. Independent correctness/Ponytail review
closed deadline and cancellation findings; its final affected-flow check passed
237 tests and five independent probes. Installed RC2 qualification is pending.

## Method and exact-device scope

The prerequisite [H6199 investigation](h6199-support-findings.md) supplied the
method: trace actual callers and exact-model APK routing, distinguish command
acceptance from fresh state, reproduce deterministically, then compare with a
real device and withdraw hypotheses contradicted by it. Its fixed white-balance,
music, DIY and dedicated segment-rollback findings are not presumed unfixed here.
Three parallel reviews covered shared runtime, Kaitai/APK structure, and features.

APK evidence is Android **7.6.01**, decompiled sources under
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources/`. `A/` below means
that root. The tested cupboard-skirt **H617A** reported **HW 3.01.01**, **FW
3.02.24**, and advertised **Pact type 10/code 1**. Five three-record segment
pages confirmed 15 logical segments. These are not 15 independently established
physical ICs, and this qualification does not cover older revisions or H617E.

Home Assistant was **2026.9.2**, with integration runtime **7.6.0rc2**. Its target
config entry was disabled for exclusive direct BLE access through host BlueZ
`hci0`, then re-enabled. The live recovery proof imported the reviewed **v7.6.0
worktree**, not the installed RC. It used real BLE writes, notifications,
capture/restore and refresh methods; only connection acquisition, HA scheduling
and logging were adapted to the isolated harness. No failing effect upload was
required to demonstrate that recovery itself destroys a mixed layout.

Evidence labels:

- **Device + code:** physical register behavior and the real reviewed code agree.
- **Software:** deterministic parser/coordinator/compiler proof or an explicitly
  identified source trace; no induced physical radio failure.
- **APK:** reachable app control/producer/consumer, not firmware implementation.
- **Deferred:** needs missing original payload, visual observation, exact geometry
  or another attributable revision. ACK is never applied-state evidence.

## Ranked actionable findings

**Scope clarification:** “effect recovery” here means the integration trying to
put the light back as it was **after applying an effect or profile in Effect
Studio fails, once device writes may have started**. It is not reconnecting
Bluetooth, restarting Home Assistant, or an ordinary successful mode change.
The sole production caller of `async_restore_effect_control_state()` is
`effect_runtime.py:_async_finish_failure`. R4 is a different operation: reverting
Home Assistant's in-memory values after an ordinary colour command raises an
error; that does not itself send the old colours back to the strip.

| ID | Priority | Finding | Strongest evidence |
| --- | --- | --- | --- |
| R1 | P1 | Effect recovery drops segment topology and flattens a mixed static layout | Device + code |
| R2 | P1 | Static recovery reports success without checking restored segments or master brightness | Device + code; ignored-write software case |
| R3 | P2 | Mixed fresh segment colors leave an incompatible aggregate Kelvin value | Device + code; entity replay |
| R4 | P2 | Whole-strip write-error rollback reinstates stale `observed` segment authority | Software fault injection |
| R5 | P2 | Spectrum/Rolling fixed-color editor controls are hidden despite working backend/register support | APK + software + device readback |
| R6 | P2 | New-music replies are overinterpreted; restoring the previous music effect after a failed Effect Studio application lacks its complete settings | APK + software/source trace |

P1 denotes loss of a user's existing state or false recovery success, not
irreversible hardware damage. Fix R1 and R2 together; snapshot fidelity and
verification are independent requirements.

### R1–R3: physically reproduced recovery failure

`CC/coordinator.py:292-341` captures aggregate RGB/Kelvin but no segment colors
or relative brightness; `CC/effect_deployments.py:84-135` has no such fields in
`PriorControlState`. The real deployment path captures this DTO and calls the
restore method after failure (`CC/effect_runtime.py:503-529,780-844`).

Direct experiment:

1. Write ordinary 4000 K. All 15 queried segments are RGB `(255,205,166)` at
   relative brightness 100. Retain the commanded Kelvin as the integration does.
2. Paint only the first segment blue and explicitly query all five pages.
   Observed state is blue followed by 14 warm segments, yet retained Kelvin is
   still 4000. Complete mixed observations bypass the uniform-only invalidation
   check at `CC/coordinator.py:1056-1082`.
3. Call the actual `capture_effect_control_state()`, then
   `async_restore_effect_control_state(prior, overwritten_diy_code=None)`.
   Recovery writes power, master brightness and **whole-mask 4000 K**. It returns
   **True**, querying only `AA01` and `AA05`.
4. Independently query segments: all 15 are warm again. The blue segment was
   erased by recovery even though no preceding effect upload changed it.

`CC/coordinator.py:620-640` restores one aggregate color and supplies no segment
or brightness expectation. H617A has neither direct-static RGB nor Kelvin
readback enabled (`CC/const.py:288-346`); default confirmation therefore proves
power/mode, not restored appearance. A separate fake-radio check ignores the
color write entirely and still gets `True`. No `AAA5` or `AA04` query is sent.
Relative-brightness arrays also disappear from the DTO; their physical loss in
a failed effect transaction was not separately induced.

`CC/light.py:320-337` exposes the retained Kelvin as active `COLOR_TEMP`, and
`:782-796` can reuse it when clearing an effect. A mixed array cannot satisfy
the intended “retain Kelvin while its RGB companion matches” rule. This is not
a request to manufacture a single RGB representation of a mixed strip.

**Correction direction:** preserve the existing restorable segment state in the
existing DTO, restore it with existing grouped commands, and require fresh
complete segment plus master-brightness evidence before claiming recovery.
Invalidate incompatible retained Kelvin on mixed observations. Unknown original
state must remain unknown rather than become a successful restoration claim.

### R4: sibling whole-strip rollback remains affected

`CC/light.py:188-196,244-289,1036-1076` snapshots and restores segment arrays,
source and observation timestamp after a whole-strip RGB/Kelvin error. A fake
GATT write applies the command and raises `BleakError` on all three attempts.
The real entity method raises, but reinstalls the old colors and old `observed`
timestamp, without a segment refresh. An error cannot prove the write did not
apply. This ambiguity was not forced on the physical device.

**Wording correction:** the timestamp is not advanced, so “as though they were
just checked” was inaccurate. Keeping the old colours as *last known* values is
reasonable. The missing step is invalidating their current-state certainty after
a write may have applied, then querying the strip. If validation or connection
setup fails before any write attempt, retaining the old state is appropriate.
The software proof covers an attempted whole-strip write that takes effect in
the fake device before the Bluetooth call raises; it does not claim every failed
command changes the real strip.

The dedicated segment paths at `CC/coordinator.py:2533-2548,2581-2595` already
reconcile attempted writes; their earlier fix is valid. Reuse that provenance
rule in the whole-strip path instead of restoring pre-write authority.

### R5: fixed-color music metadata

`CC/effect_catalogue.py:231-239` requires a music variant for `colour=true`, but
`CC/music_commands.py:94-102` and `CC/generated_protocol_adapter.py:1239-1248`
allow fixed color without a variant. H617A Spectrum/Rolling have no explicit
variant. The frontend hides the control and can reject a saved fixed-color
profile (`frontend/src/music-profile-editor.ts:91-128`,
`effect-editor-model.ts:118-138`, `panel-model.ts:460-469`).

Exact APK old-mode editors permit fixed color; direct selector-only writes for
Spectrum and Rolling at sensitivity 50, RGB `(32,96,160)`, returned that exact
mode, sensitivity, fixed flag and RGB via **both** mode-query discriminators.
This proves register support, not a visually observed microphone animation.

Software proofs also demonstrate the mismatch for H617E, without qualifying its
hardware. **Energetic is narrower:** backend accepts fixed color but the exact
H617A APK deliberately omits its edit button. Reconcile that contract rather
than automatically exposing an unsupported Energetic control.

### R6: selector authority and companion preservation

`A/com/govee/dreamcolorlightv1/ble/SubModeMusicV3.java:142-152,190-208`
writes/reads only ID and sensitivity for new IDs `30/31/32/33/34/35/37`.
Legacy byte 6 is a zero/nonzero fixed-color **flag**, not a palette count.
`KSY/govee_common.ksy:20-33` instead applies legacy style/count/RGB to all modes.
`CC/coordinator_status.py:198-209` consequently treats a zero-padded new-mode
reply as an observed color clear (`CC/coordinator.py:1214-1224`). Actual palette,
background and style live in A3 subtype `41`, not this suffix.

The APK restores those parameter bodies from **app-local storage**
(`A/com/govee/base2light/ble/music/AbsNewMusicEffect.java:119-210,360-391`), not
a demonstrated BLE read endpoint. Integration encoding reparses a fixed template
(`CC/generated_protocol_adapter.py:1319-1351`), captures only declared parameters
(`CC/music_semantics.py:273-282`), and has no full music-body preservation route.
The unknown-palette guard (`CC/coordinator.py:357-380`) is conditional on
`palette_bounds`, absent on H617A. Restoring the previous music effect after a
failed Effect Studio application can therefore replace unknown settings with
template fields and confirm only the mode. This is a source-proven preservation
gap; no resident music payload was overwritten for this review.

#### Music recheck: replacement is not inherently a defect

The previous summary “changing a music setting can replace other custom
settings” was too broad. Distinguish these user actions:

| Action | Intended behaviour |
| --- | --- |
| Select a different effect or apply a complete saved profile | Stop the old active effect and apply the chosen settings. Defaults are legitimate when the chosen profile requests them; do not merge arbitrary settings from the previous effect. |
| Edit one setting within a known profile | Keep the other settings in that profile. The current frontend already clones the profile and changes the selected field (`frontend/src/music-profile-editor.ts:343-386`). |
| Change a device setting whose other music settings are unknown | A short setting-only command can leave the other settings alone. If a complete upload is needed, applying a defined preset is valid, but it is not an exact edit of the unknown device configuration. |
| Put back the previous music effect after an Effect Studio application fails | Use its complete known settings, or report that exact restoration cannot be established. Defaults are not a substitute for unknown original settings. |

The reachable APK distinguishes these operations:

- Its sensitivity handler copies the current mode and changes only sensitivity
  (`dreamcolorlightv1/adjust/ui/MusicFragmentV3.java:66-73`). The copy does not
  include the full music body (`dreamcolorlightv1/ble/SubModeMusicV3.java:101-109`);
  a new-mode command contains only mode and sensitivity (`:142-145`).
- Hopping's editor loads the saved effect for this device/mode, falling back to
  defaults only if missing/invalid. Its brightness slider changes only background
  brightness, and its colour picker changes only background colour
  (`base2light/view/DialogRgbic4YueDong.java:101-142,162-182`). Apply sends the
  resulting complete object, including its palette
  (`base2light/view/AbsMultiMusicEditDialog.java:82-97,148-155,252-254`).
- Switching music effects loads the *destination effect's* saved settings
  (`base2light/light/v1/AbsNewMusicFragment.java:1239-1253` →
  `AbsNewMusicEffect.java:126-210,360-391`), rather than mixing in the old effect's
  settings. Defaults are created if no valid saved configuration exists.
- These are phone-local saved settings, not a full read of the strip. Another
  controller's changes can therefore be replaced by the app too. APK behaviour
  does **not** establish cross-controller preservation or exact restoration.

Repository caller recheck: `async_apply_music_params()` is called only by a test,
not a production slider/service. Do not present its template rebuild as a
currently exposed one-field-control bug. Effect Studio deliberately compiles
complete music profiles (`music_commands.py:78-103`); choosing template defaults
is legitimate replacement. The H617A template's uneditable palette/background/
gradient is a feature limitation, while substituting it for unknown original
settings during failed-application restoration is a correctness problem.
Selector-only fallback selection and full-profile application also differ
(`light.py:756-775`, `coordinator_modes.py:202-244`); not every selection uploads
the full music configuration.

Separate limitations: music recovery verifies only mode (`coordinator.py:576-587`);
initially-off recovery restores only power (`:521-524`). Neither establishes
hidden-mode or full payload equality. The aggregate pre-mode snapshot in
`coordinator_modes.py:189-192,336-347` has only a narrow music-off caller; do not
turn it into a separate untraced service defect.

## Additional BLE authoring/features

The exact music roster is already complete: four legacy modes plus seven new
modes. Sensitivity **0..99** is correct. These additions concern parameters,
not newly discovered onboard mode IDs.

| Candidate | Current gap and qualification |
| --- | --- |
| Seven new-mode palettes | Exact dialogs expose 1..8 RGBs. H617A has no `palette_bounds`; backend rejects authored palettes and UI hides its existing palette editor. Lower writer fixes count to captured 5/7 colors, so a flag alone is insufficient. Nine synthetic bodies parsed successfully. APK + software; A3/visual qualification deferred. |
| Piano Keys gradient | Named in `music_body.ksy`, but only key count is exposed in `music_semantics.py:84-90`. Exact dialog has a gradient switch. Distinct from excluded global gradual. APK + software; deferred upload. |
| Hopping background/no-color | Schema names background RGB, but only brightness 0..50 is authorable. Exact dialog offers RGB/no-color; no-color serializes `01 01 01`, although UI treats channels ≤1 alike. Preserve bytes instead of normalizing to black. APK + software; deferred upload. |
| Seven named DIY templates | Brilliant/Colorful (501), Colorful Sky (502), Meteor (503), Meteor Shower (504), Shine (505), Bloom DIY (506), Stack (507). Exact DIY v2 path uploads A3 subtype **02**, then scene selector; these are not new Type04 families. Generic layered representation overlaps, but named authoring/carrier parity is missing. APK Stack seed and authored two-layer candidate round-trip offline; no upload/activation qualification. |
| Masked Kelvin | Existing lower writer supports it; public segment services expose RGB/brightness only. Direct 3000 K on the first segment produced `(255,185,105)` there, leaving 14 warm siblings untouched across all five pages. Device-qualified rendered RGB, not native per-segment Kelvin persistence. |
| Chase palette bound | Exact DIY v2 UI caps Chase at 3; repository allows 8 and defaults to 7. Software/APK contract difference, not proof firmware rejects >3. Requires backed-up payload and rendering comparison. |
| Revision-aware scene/read admission | App has narrow conflicting HW gates; repository H617A profile/scene records do not encode them. Tested modern revision passes all cited gates. No old-device failure or blanket cutoff established. |
| Light-count diagnostic | `AA0F` freshly returned **15**. Currently raw/unnamed in the generated status envelope, not a semantic observation. APK stores this in a separate field from physical IC metadata. Optional diagnostic, not a geometry-setting authority. |

Exact feature paths (all under `A/com/govee/`):

- `dreamcolorlightv1/adjust/ui/MusicFragmentV3.java:44-94` →
  `base2light/light/v1/AbsNewMusicFragment.java:756-786,1011-1075,1148-1177`.
  `base2light/view/AbsMultiMusicEditDialog.java:132-155` supplies 1..8 colors;
  `DialogRgbic4GangQinJian.java:73-79` supplies Piano gradient;
  `DialogRgbic4YueDong.java:82-128,162-182` supplies Hopping background.
  `base2kt/utils/ColorUtils.java:185-187,418-421,794-796` defines no-color.
- `dreamcolorlightv1/adjust/v1/UiV3.java:402-404` →
  `dreamcolorlightv1/adjust/Diy.java:233-336` is **fixed DIY version 2**;
  the firmware-selected UiV1 roster is not the reachable caller.
  `base2light/ac/diy/DiyM.java:1087-1117` maps named templates;
  `base2light/ble/ScenesOp.java:514-523` selects their upload controller;
  `dreamcolorlightv1/adjust/v1/BleOpV3.java:315-337` activates after success.
  Template editors are `base2light/ac/diy/v1/ViewDiy{Colorful,Sky,Shine,Bloom,Meteor,MeteorRain,Stack}Edit.java`;
  serializers/seeds are `base2light/ac/diy/v2/ParamsV2.java:1170-1237,1304-1329,1521-1588,1699-1778`.
- Masked Kelvin: `base2light/light/v1/AbsColorFragmentV13.java:311-315` →
  `dreamcolorlightv1/adjust/ui/ColorFragmentV3.java:79-94` →
  `dreamcolorlightv1/ble/SubModeColorV2.java:521-546`.
  Repository: `CC/generated_protocol_adapter.py:878-912`,
  `CC/light_commands.py:99-102`, `CC/light_services.py:47-65,88-104`.
- Light count: `dreamcolorlightv1/adjust/v1/BleOpV3.java:706-736,374-383` →
  `dreamcolorlightv1/ble/LightNumController.java:12-25`; `ExtV3.java:35` defaults
  that field to 15. It is not the `SkuIcManager` physical-IC value.

The seven templates expose different palettes/backgrounds, brightness ranges,
speed/direction and IC-dependent areas. Reuse layered structures when adding
them; qualify their actual 501..507 carriers rather than equating a generic
Forest/Workshop upload with native template playback.

## Kaitai versus APK ledger

KSY remains the sole wire-layout source. Known field semantics below belong there;
exact-model authoring permissions and captured defaults remain separate policy.

| Finding | Evidence and disposition |
| --- | --- |
| Mode query `AA0501` vs repository `AA0500` | App `base2light/ble/controller/AbsModeController.java:34-40`; `KSY/status_query.ksy:18-40` rejects 01. Both queries produced identical scene/static/Spectrum/Rolling replies live. **Withdraw behavioral incompatibility on tested revision**; retain schema/app difference. |
| Static Kelvin bytes constrained to zero | `dreamcolorlightv1/ble/SubModeColorV2.java:595-601` reads big-endian Kelvin at absolute offsets 4..5; `KSY/status_reply.ksy:88-95` treats them as zero padding. Synthetic nonzero 4000 K reply rejects. Actual 4000 K reply has zero there with both queries. **Withdraw discarded live Kelvin**; direct Kelvin observation remains unqualified. |
| Known music-tail fields fixed/opaque | See table below. Captured templates are valid examples, not parser-wide invariants or app reset defaults. Synthetic Hopping speed 0x61/Piano speed 0x0B reject. No physical alternate geometry/speed qualification inferred. |
| Ordinary/A3 ACK semantics | APK `base2light/ble/controller/AbsSingleController.java:40-49,68-69` uses ordinary byte 2; `AbsMultipleControllerV2.java:24-31` uses A3 byte 3, zero success. H617A lacks an ACK root; ordinary ACKs parse as writes/echoes, A3 replies reject as status. Real successful ordinary ACKs observed. Callback logs only: **no ACK-as-power-off mutation**. Negative-result/transaction handling remains deferred. |
| Upload order | Exact app `UiV3.java:1313-1322`, `BleOpV3.java:508-524`: upload → positive result → selector. H617A integration defaults to selector → upload. Source difference, not demonstrated activation failure. |
| Layer brightness/selection semantics | `KSY/govee_shared.ksy:75-89,121-124` leaves known meanings opaque. `base2light/ble/ScenesRgbIC.java:4227-4266` decodes brightness high nibble algorithm 0/1/2 and low nibble type 0..3. `ParamsV2.java:735-743,978-992`: selection types 0/1 use BE u16 selection/IC quantity; type 2 uses random min/max bytes; type 3 uses piece/gap IC counts. Raw round-trip is preserved; semantic naming/editing gap, not byte loss. |
| Color distribution mask | `ParamsV2.java:339-384,414-426` uses low **four** bits plus bit 7 direction; schema/canonical model names low seven bits as method. Preserve bits 4..6 as extensions rather than expanding known method enum. Current authored 0..3 agrees. |
| Flat DIY zero sequence length | `base2light/ac/diy/DiyProtocol.java:48-80` always emits it; `KSY/diy_type04.ksy:33-49` treats flat's zero as padding. Current ≤8-color packet bytes/counts agree through zero padding. Nine-color boundary changes chunk count but exceeds exact-app authoring bound; no current exposed packet failure. |
| Type03 labels/geometry | `DiyGraffitiV2.java:41-48,210-258` names base/background brightness and IC addressing; schema calls them brightness/segment indices. Layout matches. Existing 15-address qualification is valid; no physical IC expansion inferred. |
| Gradual retention wording | `AA A3` decodes but has no normal H617A semantic read/recovery domain; documentation saying raw state is retained must not imply full recovery retention. Baseline zero queried/restored unchanged. Exposed gradual remains excluded by exact app and prior visual evidence. |
| Strict unused/tail zeros | Segment layout really is three brightness/RGB records plus four unused bytes. App ignores tail, schema validates zero; all live pages match. No nonzero counterexample, no reason to invent extra segments or relax all validation. |
| A3/type1 structure | 17-byte fragments, final FF, and empty terminator agree with app. Type1 raw/config preservation works for qualified strides. Generic APK parser acceptance of more layouts/strides is not exact-H617A compatibility. |

Music tails follow palette count/RGBs; APK sources are under
`A/com/govee/base2light/ble/music/`, repository `KSY/music_body.ksy:54-112`:

| Mode | APK field semantics and source | Current narrowing |
| --- | --- | --- |
| Bloom | no-rhythm/rhythm speeds, `RgbMusicZhanFang.java:9-24,51-85` | Literal 0A + style companion |
| Shiny | min/max brightness, speed, `RgbMusicCuiCan.java:9-25,48-76` | Brightness pair conflated into u2 style; speed literal |
| Separation | point, fade, IC-dependent speed, `RgbicMusicFenLi.java:21-30,58-97` | Speed called companion |
| Hopping | background RGB, brightness, speed, piece-length min/max, piece-count min/max, `RgbicMusicYueDong.java:77-94,121-159` | Final five bytes literal `62 01 03 02 06` |
| Piano | fade, keys, speed, off-min/off-max, `RgbicMusicGangQinJian.java:68-106,123-140` | Speed/off-min literal; off-max called half, actually `max(off_min, keys//2)`; equivalent for qualified 8..15 range |
| Fountain | start/direction, piece length/count, speed, `RgbicMusicDuiJi.java:13-22,41-106` | Length pinned to 1; physical IC affects alternatives |
| Day/Night | piece count, speed, fade, `RgbicMusicZhouYe.java:59-93,117-130` | Piece count named segment count |

IC metadata comes from `AbsNewMusicFragment.java:1262-1264`/`SkuIcManager`, not
logical segment count or `AA0F`. Differences between capture templates and APK
factory defaults (5 vs 7 colors, brightness, key count, direction) are preset
differences, not failures. Preserve unknown original companion fields before
claiming settings-exact restoration.

## Shared-code approach: representative examples, not an exhaustive audit

Treat this as one cross-model concern: **shared packet handling must not silently
impose one product's limits, feature combinations, or meaning of a reply on
another product**. The examples below illustrate failure patterns, not a backlog
of every literal value or a proposal for a new abstraction layer.

| Pattern to look for | Representative evidence | Approach |
| --- | --- | --- |
| A device declaration is honoured at one layer but overridden below it | G2's temperature range is clamped a second time; G3's model-specific segment count hits an earlier global cap | Follow one request from UI/service validation through the writer. Use the effective device declaration consistently; distinguish product limits from genuine packet-format limits. |
| Independent abilities are bundled together | G1 requires segment writes before segment reads work; R5's editor requires variant metadata although the writer supports the colour setting without it | Make the existing UI, validation, reading and writing paths agree on the particular ability being requested. Reading, writing and confirming a result are separate abilities. |
| One example packet becomes a universal rule | Fixed music palette lengths/tail values; legacy music reply meanings applied to newer modes | Put evidenced structure and field meaning in Kaitai, product permissions in profiles, and example/default values in presets. Do not interpret missing information as a reported reset. |
| A shared operation keeps only the state sufficient for simpler devices | R1's whole-strip snapshot omits per-segment state; R2 confirms mode rather than appearance | Trace capture, writes and confirmation together. Preserve everything the operation promises to restore, and verify only through the device's supported reads. |

Use a few deliberately contrasting test profiles to detect these patterns (for
example read-only segments and a wider declared range), plus real-model tests.
This checks whether the declarations actually govern behaviour without claiming
unproven hardware support. Fix the responsible shared layer and its callers;
avoid per-model exception lists or indiscriminately removing protocol guards.

### Existing illustrative proofs (synthetic profiles only)

| ID | Obstacle | Proof and boundary |
| --- | --- | --- |
| G1 | Read-only segment capability requires writes | `CC/const.py:256-264` defines `supports_segments` using write permission; `coordinator.py:1445-1448,1618-1621,2172-2174` drops replies/skips queries. Independent synthetic status key with 15/3 geometry and SEGMENTS read domain sends nothing until unrelated write permission exists. No shipped read-only SKU failure claimed. Conversely write-only paint still demands readback; completion policy is an extension question. |
| G2 | Profile Kelvin range overridden | `CC/light_commands.py:99-102` honors declared bounds; adapter `:878-898` clamps again to 2000..9000. Synthetic 1500..10000 profile encodes Kelvin 2000 with RGB computed for 1500. Current profiles fit the clamp; never probed 1500 K on H617A. |
| G3 | Global 15-segment authoring cap | `CC/light_commands.py:17-38` and service validation `light_services.py:33-45` reject segment 16 before target-specific validation. Synthetic 16-segment profile's writer round-trips mask 0x8000. This is a declaration obstacle, not evidence H617A has segment 16. |

Other extension-only traces: `ReadDomain.MODE` is declared but normal paths use
`COLOUR_MODE`; no shipped profile or independent runtime failure found. Painted
frontend exactly-15 validation matches current qualified segment-addressed
targets, with separate physical-IC authoring. Grammar allowlists select real
wire structures and should remain fail-closed; replacing them with broad
capability booleans would not make new protocols compatible.

## Identity/revision reachability and closed findings

Literal H617A registration/theme appears in
`A/com/govee/dreamcolorlightv1/pact/Support.java:246,526-529`.
`pact/SubMaker.java:27-33` → `pact/ble/V4BleSkuItem.java:4-7` registers goods 73;
`AbsBleSkuItem.java:17-24` binds SKU from product metadata. There is no literal
H617A→73 product-table assignment in this Java tree: historical exact-device
identity supplies that premise, while the live advertisement corroborates
Pact 10/1 (`Support.java:414-422`). Do not claim the advertisement encodes goods 73.
`adjust/v1/FrameV1.java:25-34` → `UiV3.java:820-836` admits this Pact;
`UiV3.java:316-322` → `ModeUiV3.java:100-112` → `MusicFragmentV3` establishes the
actual music path. Goods-73 BK routing is explicit at `Support.java:1171-1188`.

Narrow gates in `Support.java`:

- Segment read: HW ≥1.00.03 and FW ≥1.06.00 (`:1917-1927`, called by
  `BleOpV3.java:206-214`); segment write UI is selected independently.
- Legacy shared type2/cmdVersion1 scene admission: HW ≥1.00.02 and FW ≥1.06.00
  (`:1930-1943`). Version 0 accepted; other nonzero versions rejected by that path.
- Exact KMP H617A config uses HW ≥1.00.03/FW ≥1.06.00
  (`shared/config/h617a/H617ASceneConfig.java:59-61`,
  `shared/config/KmpRgbicV0Support.java:44-45,65-67,86-93`). Active KMP use in
  this legacy UI is unproven.
- Effect-square helper `Support.java:1138-1142` contains a malformed decompiled
  ternary; list association needs DEX confirmation. Do not derive a blanket
  downgrade from conflicting/decompiled gates. Repository scene metadata lacks
  `cmdVersion` (`CC/scenes.py:56-68,99-120`).

Closed/narrowed dispositions, retained to prevent repeated speculative work:

- **Global gradual #131:** exact goods73 `noSupportGradual` remains true
  (`Support.java:1529-1533`). Prior six paired visual comparisons found no effect.
  Register persistence/ACK does not reopen it. Internal music/DIY gradients are
  separate payload fields.
- **Scene type1 layout1 #125:** prior ACKed body did not replace rendering; still
  rejected. **Fountain speed #130:** 0x10/0x50 physical difference was already
  established; no newly reachable speed slider. **Area #166:** raw nibble/zero
  sentinel preservation remains valid.
- Basic DIY's **19** family/variation pairs, six Painted variants and Multi's
  four-child/six-family roster are implemented. No missing Basic family inferred.
  Basic speed 0..100 and DIY-music sensitivity 0..100 agree with the APK. Painted
  brightness zero vs UI minimum 1 is only an app-envelope difference, not a
  proven rendering failure. Black/white preset defaults are not protocol bugs.
- H617A committed scene catalogue has 83 entries (9 type0, 2 type1, 72 type2),
  50 with speed metadata; this is snapshot coverage, not cloud completeness.
- Dedicated segment rollback and historical H6199 WB/sensitivity/DIY corrections
  remain fixed. H6199 native-DIY recovery remains explicitly unqualified.
- H617E immutable-base reuse overrides exact SKU/carrier/evidence; no wrong
  inherited runtime value was demonstrated. H6099 DreamView capacity is a
  family serializer limit, not an accidental H617A segment count.
- No H617A lock, power-on-memory, cut/IC-refresh, video/camera/WB, installation
  direction, or DreamView membership controller was established. Exact support
  gates exclude lock/power-memory/cut (`Support.java:1606-1613,1960-1970,1661-1671`);
  music-feast goods roster excludes 73 (`:1690-1692,1113-1131`).
- Whole-segment brightness-vector opcode `33051503` is already structurally
  understood; masked writes express the same control. No new product feature or
  vector-write physical test claimed.
- No burst-write timing failure was measured; timeout/reconnection and general
  negative-ACK transaction limitations remain deferred, not grounds to increase
  timeouts speculatively.
- Global exclusions remain: timers, phone/host microphone, continuous streaming,
  OTA, cloud/network/account setup, AI and cloud camera calibration.

## Physical test record and restoration

Initial fresh baseline: power **on**, master brightness **5%**, scene **9
(Candlelight)**, 15 × RGB `(255,136,13)`, all relative brightness **100%**, gradual
register **0**, count **15**. Queries also included FW/HW and both mode variants.

Representative identifier-free frames are executable fixtures in
`tests/test_kaitai_protocol.py`; these are direct-device captures, **not app
captures**. Synthetic counterexamples are separately labelled there. Complete
private captures and direct tooling stay outside the repository:

- `/tmp/opencode/h617a-baseline.jsonl`
- `/tmp/opencode/h617a-probes.jsonl`
- `/tmp/opencode/h617a-live-recovery.jsonl`
- `/tmp/opencode/h617a-live-recovery.py`, `h617a-direct-run.py`, `h617a-ha.py`
- Three detailed working reviews: `/tmp/opencode/h617a-{generic,kaitai,features}-review.md`.

After **each** direct write experiment, independent restoration re-established
RGB `(255,136,13)`, relative brightness 100, scene9, master5 and power1. All
**13 baseline query results matched byte-for-byte**: power, brightness, two mode
queries, firmware, hardware, gradual, count and five segment pages. No A3
payload upload was sent; original inactive payloads were not available as a
restoration source, so music-palette/background/gradient and named-template
uploads were deferred. A scene selector is not a payload backup.

HA config entry is restored to enabled/loaded. After
`homeassistant.update_entity`, the light is on, Candlelight, HA brightness13
(5% device). Reload invalidated previous optimistic RGB/segment/retained-Kelvin
caches; the RC exposes initial white arrays in scene mode. Those initial arrays
are **not fresh physical mismatch evidence**, and original HA cache equality is
not claimed. Physical restoration was independently verified before re-enabling.
No visual observer was present; rendering/animation claims above stay bounded
to register observations or explicitly historical visual tests.

## Runnable verification and follow-up order

```sh
make protocol
uv run --no-sync pytest -q tests/test_h617a_review_proof.py tests/test_kaitai_protocol.py
make check
```

`test_h617a_review_proof.py` deliberately asserts current defects, including the
ignored-write branch, stale rollback, missing capabilities and synthetic-profile
ceilings. Update those assertions into corrected-behavior regressions when
implementing fixes. `test_kaitai_protocol.py` replays fresh mixed/masked-Kelvin and
fixed-music replies and records current APK/schema counterexamples. The full
generated-root check exercises fixtures skipped by the runtime-only parser run.

Recommended order: **R1/R2 recovery → R3/R4 provenance → R5 metadata → R6 full
music-state boundaries → backed-up one-field A3 qualification**. Then consider
named templates, schema semantics and generic profile obstacles with exact-model
evidence. A3 tests need the original complete resident upload and visual checks;
old-revision gates need attributable identities and command-version metadata.
