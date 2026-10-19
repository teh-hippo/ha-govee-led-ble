# H60A1, H60A6 and H601C candidate support

## Request and known context

These exact-model Experimental profiles are prerelease candidates awaiting device-owner
qualification. Manual addition or **Reconfigure** preserves the existing entry/entity
identity. Select the printed SKU; H601C is not H60C1. Installation and promotion follow
[CONTRIBUTING.md](../CONTRIBUTING.md).

## Research findings

Original app reference: Android Govee 7.6.01 decompiled sources, locally under
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources/`. Paths below are relative
to that source root. Decompiled source establishes static producer/parser candidates;
it does not establish physical operation or exhaustive hardware coverage.

Reporter reference: [cedhuf/ha-govee-led-ble, immutable
f8d4267309e7bac38460c728e05616d07f879b3e](https://github.com/cedhuf/ha-govee-led-ble/blob/f8d4267309e7bac38460c728e05616d07f879b3e/docs/h60a-support-findings.md).
Its findings describe owner BLE sessions and decrypted iOS app captures on
2026-10-09/10. This repository has reproduced literals from the fork's tests, not an
independently attributable raw capture artifact. Fixture attribution remains partial.

| Surface | Source evidence | Runtime disposition |
| --- | --- | --- |
| H601C identity | `com/govee/bulblightv3/pact/Support.java`: H601C goods 111; `com/govee/pact_h60a0/pact/Support.java`: H60C1 goods 324 | Exact H601C profile; no H60C1 alias |
| H601C RGB/Kelvin | `com/govee/bulblightv3/ble/SubModeColor.java:36–44,71–82,96–110` | `33 05 0d`, direct RGB, BE Kelvin, companion RGB; whole device only |
| H601C companion table | `com/govee/base2home/Constant.java:469–546,1061–1074` | All 39 first ordered entries, 2700–6500 in 100 K steps; off-table requests rejected before writes, no interpolation |
| H601C mode query | `com/govee/base2light/ble/controller/AbsModeController.java`, `p()`; `bulblightv3/ble/Mode.java` | Query layout remains decode-only; H601C runtime makes no status-readback claim |
| Basic power/brightness/identity | `com/govee/base2light/ble/controller/{SwitchController,BrightnessController,SoftVersionController,HardVersionController,AbsSingleController}.java` | H601C command grammar remains enabled for writes; status roots remain speculative and are not selected at runtime |
| H601C reported hardware check | Contributor report in [PR #330](https://github.com/teh-hippo/ha-govee-led-ble/pull/330): HW 1.00.01 / FW 1.00.07 | Reports live `33 05 00` ACK and `aa 05 0d` register confirmation; no attributable raw capture or independently verified visible-output result, so this does not qualify the model |
| H601C multi-fixture report | [PR #330](https://github.com/teh-hippo/ha-govee-led-ble/pull/330#issuecomment-6117577561): eight 6-inch downlights, HW 1.02.00 / FW 1.00.11, ESP32 proxies | Owner reports missing status replies, group-control stalls, dropped commands and proxy-slot pressure; keep controls optimistic and serialize light updates pending exact-candidate retest |
| H60A geometry | `com/govee/pact_h60a0/pact/Support.java:185–214,238–240,345–346,489–498` | Four records/page; H60A1 14, revision-authorised H60A6 13; geometry authorization separate from schema presence |
| Meaningful page records | `com/govee/base2light/kt/general_controller/Controller4ColorInfoByGroup.java:173–187` and reporter literals | Complete four-page collection required; zero-valued records count, unused slots opaque |
| H60A brightness | Reporter front-panel-only `33 04 PP`; H60A6 `aa04` always 01; masked brightness ACK/readback without rendering | One panel write; no brightness queries/retry verification; stored level retained locally, never BLE observation |
| H60A Kelvin | `pact_h60a0/pact/Support.java:495–498`; `pact_h60a0/adjust/h60a1/ColorMode.java:49–51`; `base2light/pact/newdetail/config/fuc/color/Bytes.java:185–240`; `KelvinConfig.java`, `S2`; owner-reported fork test ([#339](https://github.com/teh-hippo/ha-govee-led-ble/issues/339#issuecomment-6125571117)) | Whole-device `33 05 15 01` Kelvin enabled on revision-authorised H60A1 and H60A6; per-segment Kelvin enabled on H60A6 Pact 1/3+ and the reported HW 1.04.03 / FW 1.00.41 tuple, disabled on H60A1 where masked Kelvin blanks the sibling zone; current integration qualification remains pending |
| Encryption | Reporter advert flag 0x40, v1 handshake; existing repository transport | Existing advertisement/GATT-selected encryption; no SKU-selected plaintext fallback |

The owner later corrected the earlier `7.8.1-rc.2.lights` test as incomplete and
misattributed. Comparing that tag with `v7.9.0` shows only the manifest version
changed, so the later failures expose untested group-load behaviour rather than a
source-code regression between those builds.

### Identifiable variants and authorization

| Exact product/context | Candidate owner | Enabled scope / outstanding evidence |
| --- | --- | --- |
| H60A1 Pact 2/1 | `device_profile`, app Pact branch + 14-record geometry | RGB, whole-device Kelvin, and segments candidate; per-segment Kelvin remains disabled |
| H60A1 absent Pact, or Pact 1/1, HW 1.04.03 + FW 1.02.20 | `device_profile`, exact reporter tuple | Owner verified power/RGB on v7.11.0 and reported fork tests for whole-device Kelvin (2700–6500 K) and 14-segment RGB; current integration Kelvin qualification remains pending and per-segment Kelvin remains disabled |
| H60A1 any other/partial Pact or tuple | Restricted exact profile | Power/panel brightness only; app may describe wider geometry, deliberately not authorized by this candidate |
| H60A1 HW below 1.04.03 | App `KelvinConfig.S2` | 2200 K lower bound when Pact-qualified; unqualified revisions keep Kelvin disabled |
| H60A6 Pact 1/2 | `device_profile`, `Support.supportPartColor4H60A6` | 13-segment RGB and whole-device Kelvin candidate; per-segment Kelvin requires Pact 1/3+ or the exact reported tuple |
| H60A6 Pact 1/3 or later code | `device_profile`, `Support.supportSegmentedTem4H60A6` | 13-segment RGB, whole-device Kelvin, and per-segment Kelvin candidate |
| H60A6 absent Pact, HW 1.04.03 + FW 1.00.41 | Exact reporter tuple | Owner verified power/RGB on v7.11.0 and reported fork tests for whole-device Kelvin (2700–6500 K) and 13-segment RGB/Kelvin; current integration Kelvin qualification remains pending |
| H60A6 Pact 1/1, partial/other Pact, or unmatched tuple | Restricted exact profile | Power/panel brightness only; known 1/1 has one-zone geometry, other contexts retain candidate metadata |
| H601C basic identifiable variants | `bulblightv3` goods 111 basic producer; PR #330 reports one HW/FW combination above | RGB/Kelvin/power/brightness candidate; the reported ACK/register result does not establish visible output or qualify other variants |
| H601C Matter branch: BLE + Wi-Fi FW >=1.01.05, HW exactly 1.07.02 | `bulblightv3/newdetail/config/MatterSupport.java:142–166` | Matter eligibility only; does not change basic encoding or qualify BLE operation |

Reconnects retain cached H60A capabilities for presentation but revoke tuple-dependent
write authorisation until valid identity replies arrive on the current connection.
Prepared packets are revalidated at each physical attempt.  Pact authorisation is
independently retained.  Unconfirmed identity cannot authorise the exact reporter-tuple
route, even when its cached controls remain visible.

## Candidate support scope

H60A1/H60A6 expose power and front-panel brightness initially, and add RGB, whole-device
colour temperature (`ColorMode.COLOR_TEMP`), and segment RGB actions once revision-authorised.
Revision-authorised H60A6 (`Pact 1/3+` or `HW 1.04.03` + `FW 1.00.41`) also exposes per-segment
colour temperature (`set_segment_color_temp`), whereas H60A1 keeps per-segment colour
temperature disabled because masked Kelvin writes blank the unselected zone. Front panel
is segment 14/13; the preceding 13/12 segments are the ring. Master brightness does not
dim the ring. Segment register brightness is decoded but never offered as a rendered
brightness control.

H601C exposes whole-device RGB, 100 K-step Kelvin, brightness and power using
optimistic state only. Status queries are not enabled because the owner reports no
replies on the tested downlights; a successful write or optimistic state is not proof
of rendered output. Unknown mode/tail bytes and companion RGB remain decode-only.
Arbitrary app-authored companion state cannot be losslessly replayed through the basic
HA controls.
Authored raw H601C writes must use the canonical table companion; incoming companions
remain opaque to control recovery. An unsolicited Kelvin reply demotes old direct RGB
to retained knowledge. Power wire values remain unsigned (nonzero is on); out-of-range
brightness is rejected semantically. ASCII terminated identity strings are a conservative
query-layout hypothesis; nonterminated or differently encoded identity remains unqualified.

Effects, music, scenes, DIY/Workshop, separate zone power and H60A6 133-point paint are
unavailable.  The exact-SKU [H601C catalogue](../custom_components/ha_govee_led_ble/scene_catalogues/H601C.json)
retains all 66 vendor scene entries across six categories as inert metadata.
It is refreshable through the existing catalogue tool but is not loaded into runtime
scene selectors or Effect Studio.  Catalogue data does not qualify BLE upload,
activation or readback; these paths remain disabled.
Thirteen logical H60A6 segments are not its 133 paint points. The reporter
paint upload, activation, point mapping and rendering need independent KSY and owner
qualification. H60A segment brightness and H60A1 per-segment Kelvin remain disabled due
to known rendering or sibling-zone failures. App clock/session setup, bulk status, Wi-Fi/Matter provisioning,
timers and firmware updates are outside this candidate; repository non-goals still apply.

## Model-specific changes and owner checks

| Obligation / semantic flow | Implementation owner | Runnable software evidence | Remaining authority |
| --- | --- | --- | --- |
| Exact profiles / revocation | `const.py`, `coordinator.py` | `tests/test_ceiling_profiles.py` | Fresh reported Pact/HW/FW plus physical controls |
| H601C write → optimistic HA state | speculative `h601c_command_write.ksy`, adapter and light commands; status root not selected at runtime | `tests/test_h601c_protocol.py` (static-derived vectors, not captures); profile tests enforce no query/readback claims | Owner RGB/Kelvin output and restoration; grouped writes across more than three proxy-routed lights |
| H60A pages → complete state → masked writes | speculative `h60a{1,6}_status_reply.ksy`, shared command root, coordinator | `tests/test_h60a_protocol.py` (reporter literals plus explicitly synthetic pages) | Attributable full page sequences and visible ring/panel behavior |
| Write-only brightness / invalid preflight / rollback | `light.py`, shared physical writer | Ceiling entity tests; existing `tests/test_light.py` and coordinator tests | Owner panel dimming, restart-retained value, no ring dimming claim |
| Reconnect / stale profile | Authorization identity invalidation and per-attempt guards | Reconnect revocation regression and late identity tests | Real reconnect with missing/changed identity |
| Build/import closure | Runtime root/output lists and production adapter imports | `make check`, `make package`; no test-only production registration | Published exact-SHA ZIP/checksum |

Audits corrected missing production H60A roots, hidden brightness-only controls, off-grid
H601C writes, stale tuple authorization across reconnect, post-await optimistic overwrites,
and basic-request side effects before validation. Brightness restoration is retained-only;
late H60A profile qualification preserves that level. Deferred findings remain above:
companion replay, wider app geometry, paint/effects, identity encoding/availability and
physical revision coverage. Tests establish software boundaries, not hardware support.
Shared exact effect-state restoration fails closed before appearance writes for H60A: segment RGB
alone cannot identify the original white-emitter mode, and segment-brightness/mode reads
are not qualified. Off-state recovery may still send power-off cleanup. This is not a
complete app-state backup/restore implementation.

Explicit app registrations are H601C Pact 1/1 and 2/1 (`bulblightv3/pact/Support.java:130–135`),
H60A1 1/1 and 2/1 (`pact_h60a0/pact/Support.java:135–140`), and H60A6 1/1, 1/2, 1/3
(`Support.java:150–158`). Future H60A6 codes follow the app's predicate but are not observed
variants. Reporter documents do not give Pact tuples. Synthetic unknown-Pact tests do not
create identified hardware variants. H601C companion interpretation is independently
corroborated by `bulblight/mode/ModeParseStrategyConfig.java:58–64`.

Reproduce with `make check` and `make package`; focused replay:
`uv run pytest tests/test_ceiling_profiles.py tests/test_h60a_protocol.py tests/test_h601c_protocol.py -q`.

Owner validation: install the exact prerelease through HACS beta versions, restart, add or
reconfigure the exact SKU, then try power, brightness, RGB and the enabled segment/Kelvin
controls. Test ring and panel independently on H60A, H601C RGB ↔ Kelvin at 2700/4000/6500,
off/on, reconnect and restart. For H601C, also exercise grouped actions across the
proxy-routed fixtures and report latency, dropped commands and restoration. Confirm physical
output as well as HA state and restore the starting state. After a failure export redacted
diagnostics immediately, including exact release, Pact/hardware/firmware and expected/observed
behavior. Do not share unique device identifiers. Owner results remain required for support-status
promotion; maintainer-approved stable inclusion does not qualify the implementation or its evidence.
