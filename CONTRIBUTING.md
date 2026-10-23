# Contributing

## Requesting support for another model

Open one GitHub issue for the exact model and apply its exact SKU label (for example `H617A`, `H6199`, or `H6076`); pull requests for a specific model should carry the same SKU label.  Include:

- the SKU printed on the device;
- the BLE local-name prefix with its unique suffix removed, for example `Govee_H617P_...`;
- firmware and hardware versions;
- whether the Govee app offers an update;
- which controls already work or fail; and
- whether you can test candidate changes on the physical device and report results.

Do not post the Bluetooth address, serial number, account details, or other unique identifiers.

## Project structure

- `custom_components/ha_govee_led_ble/const.py` owns the exact-model `ModelProfile` registry.  Profiles declare product capabilities and runtime policy; `command_grammar` and `status_grammar` independently select compatible outbound and inbound protocols.
- `tools/ble/kaitai/**/*.ksy` is the only BLE wire-structure source.  Generated modules under `generated_protocol/` are build outputs and are never edited manually.
- `generated_protocol_adapter.py` connects generated structures to semantic builders and parsers.  Handwritten protocol code is limited to semantic transforms, checksums, and transport framing.
- `coordinator*.py` owns connection lifecycle, queries, notifications, state, verification, and diagnostics.
- `light.py`, `light_services.py`, and the model profile expose only capabilities declared for the configured device.
- Effect Studio uses the same model profiles, capability contracts, and exact-SKU catalogues rather than a separate model architecture.
- `scenes.py` loads committed exact-SKU Govee snapshots.  Catalogue data and BLE transport evidence remain separate.

Every exact SKU has its own profile, support quality, catalogue identity, and product capability data.  Compatible models may share a Kaitai wire adapter, but do not share whole profiles or exact-SKU metadata.

### Protocol, profile, and wire invariants

- **Kaitai owns wire structure and codebooks:**
  Command frames, status replies, upload acknowledgements, mode and scene codebooks, companion mode enums, and register bounds live in `.ksy` schemas under `tools/ble/kaitai/`, never in handwritten Python tables or entity/coordinator offsets.
  Shared builders keep logical domain values; register rescaling (`brightness_wire_range`, `kelvin_direct_rgb`) and frame transforms re-encode through exact-model KSY wire roots.
- **Profiles own product capabilities:**
  Every SKU explicitly declares its own `ModelProfile` in `const.py` and, when it exposes Effect Studio or DIY/music effect parameters, its own `ModelEffectCatalogue` in `effect_catalogue.py`.
  Grammar keys (`command_grammar`, `command_ack_grammar`, `status_grammar`, `bulk_status_grammar`, `setting_grammar`, `effect_grammar`, `music_grammar`, `video_grammar`, `dreamview_grammar`) independently select codecs and fail closed on unknown keys without granting product capabilities or inheriting another SKU's catalogue.
  `device_profile()` narrows capabilities from confirmed Pact, hardware, and firmware identity (`profile_identity_fields`).
  Cached identity stabilises UI presentation across polls and Release-mode disconnects, while operation admission and physical writes require current-connection confirmation.
  State-readable devices default to Release mode and use Hold mode only when configured for periodic polling.
  Readable power does not imply observable effect activation.  A mode or selector reply confirms selection, not uploaded content, speed, or rendering.
- **Shared routing and wire invariants:**
  Construct and validate the complete immutable request against the effective profile before cancelling previews, acquiring user control, or mutating state.
  All outbound BLE writes pass through `GoveeBLECoordinator._async_write_packet` and optional synchronous, stateless `outbound_transform` hooks, installing packet-specific optimistic state and command expectations only at the physical write boundary after guards and transformation succeed.
  `tests/test_profile_wire_invariants.py` verifies every registered `ModelProfile` and explicit `device_profile()` revision case end to end against its selected Kaitai schemas (add a case whenever `device_profile()` introduces a new runtime-distinct outcome); extension tests register isolated test-only profiles and status roots rather than mutating production allowlists.

## Planning support for a new model

Use the same short structure for human and agent plans:

1. **Request and known context**
2. **Research findings**
3. **Candidate support scope**
4. **Model-specific changes and owner checks**

Research the exact device through available app behaviour, public sources, related projects, and supplied material.  Review contributed protocol files rather than accepting them as authoritative.  Always target full in-scope support across all hardware and firmware revisions, enabling every defensible capability backed by exact-model protocol evidence or speculative Kaitai on both `Experimental` and `Supported` models while keeping only disproven or unsafe operations disabled.  Preserve unknowns instead of inventing facts.

The plan should describe only model-specific findings and work.  Keep the plan in the issue or pull request discussion rather than committing per-model files under docs/.  Link to this document instead of repeating repository architecture, protocol, support, release, or validation rules.

## Support lifecycle

| Status | Meaning |
| --- | --- |
| Experimental | Candidate support awaiting owner confirmation on hardware. |
| Supported | Confirmed working on hardware by a device owner. |

The progression is:

1. A device owner requests an exact model and volunteers to test on hardware.
2. A contributor or maintainer researches the known device surface and builds the broadest candidate that can be modelled without fabricating protocol facts.
3. New model candidates and speculative Kaitai schemas merge directly to `master` as `Experimental` once `make check` passes; no blocking prerelease gate is required before merging.
4. The owner tests the available features on hardware and reports any failures with redacted diagnostics.
5. Failed capabilities are fixed or removed, and the model is promoted to `Supported` once confirmed working on hardware by a device owner.

Prerelease versions are stamped only in packaged artifacts when published for targeted testing; feature branches and `master` retain the current stable source version.

## Device-owner validation

The first validation request should stay short: provide the release or build link, explain installation or reconfiguration, ask the owner to try the available features, and request redacted diagnostics immediately after anything fails.  Include the privacy warning above.

Use a targeted follow-up checklist only when a result needs clarification.  Ask for the action, expected and observed result, Home Assistant state, restoration result, exact version, and immediate diagnostics.  Device owners are not expected to build the repository or run its developer test suite.

If the config entry never loads, enable debug logging for
`custom_components.ha_govee_led_ble` and copy only the address-free protocol
rejection lines.  Do not attach a complete unredacted Home Assistant log.

## Protocol evidence and speculative schemas

Model numbers, catalogue grouping, and related-model behaviour are clues, not
compatibility proof.  A related model may share power commands while using
different colour, segment, scene, or readback structures.

Enable each capability independently.  Document failures as well as successes so known gaps remain unexposed.

The repository has two protocol evidence classes:

- `tools/ble/kaitai/*.ksy` contains evidence-backed H617A, H6199, and independently verified shared structures.
- `tools/ble/kaitai/speculative/*.ksy` contains exact-model hypotheses for `Experimental` candidates and `Supported` models whose wire paths have not yet been promoted from official-app BLE captures.

When no official-app BLE capture is available, model the full known exact-model surface as far as the available evidence permits.  Every enabled wire path must use exact-model speculative KSY or a genuinely compatible evidence-backed root.

Every speculative KSY must begin its top-level `doc` with `SPECULATIVE`, name
the exact model and support issue, state the compatibility hypothesis, and list
unresolved assumptions.  Preserve uncertain bytes as opaque or unknown data.
Do not invent enum members, semantic names, `reserved` fields, or `valid`
constraints.

Speculative roots may be generated into the runtime package, and only roots
used by an enabled profile path belong in the runtime root list.  Enable all
defensible in-scope capabilities backed by exact-model speculative schemas or
compatible evidence-backed roots, keeping only disproven or unsafe paths
disabled.

Promoting a schema to the evidence-backed parent directory requires attributable
official-app captures, representative direct-byte parser tests, successful
owner qualification, and explicit documentation of every enabled path.  Follow
the public [`ios-ble-capture` methodology](https://github.com/teh-hippo/ios-ble-capture/blob/main/docs/methodology.md).

Diagnostics retain bounded raw transmit and receive frames, including parser
rejections.  Raw hex is the replay input: after correcting a KSY, add the
relevant frame directly to `tests/test_kaitai_protocol.py`.  Do not commit
packet captures, diagnostics exports, or a second protocol representation.

Do not add offsets, command literals, or packet enums to entity or coordinator code.

Review the complete semantic path, not just generated packet equality:
named fields -> observations -> sibling preservation -> persisted recovery ->
generated writes -> fresh verification. Classify each relevant field as
applied, preserved, decode-only, or unknown. Include a differential replay when
two replies differ only in a mode/flag that recovery must retain. Legacy missing
fields stay unknown; restored values never become fresh observations. Test
partial writes and complete-but-mismatched readback, not only missing replies.
Independent master and zone-enable flags stay independent in controls and recovery.
Abandoned segment or bulk queries quarantine their subscription until reconnect; late replies never make it reusable.
Deliberate effect Apply may skip unrelated ambiguous segment reads, but must retain fresh recovery snapshots for models with unambiguous static readback.
Preview requires fresh native zone flags and a restorable mode, even when a selector alone can be observed.
An aggregate Kelvin value or RGB segment page cannot establish every zone's native-white intent.
Do not expose a persistent palette-bound scale control without independently reachable safe requalification after normal Release-mode disconnects.
Keep every investigation finding in its verification ledger, including deferred
paths and the evidence or approval needed to qualify them.

## Exact-SKU scene catalogues

Scene catalogues come from Govee's exact-SKU catalogue endpoint through the existing repository tool:

```bash
make protocol
uv run python tools/ble/refresh_scene_catalogues.py H6179
```

Commit the full generated snapshot.  Do not copy another model's catalogue or
hand-select a subset.  Catalogue availability proves scene identity and vendor
payload data only; it does not prove transport, activation, upload, or readback
compatibility.

Enable scene activation and upload whenever an exact-model transport hypothesis
or verified grammar is represented in Kaitai, while keeping disproven or unsafe
paths disabled.  Owner-confirmed visible behaviour and restoration are required
before promoting an Experimental model to Supported.

Use `scene_codes` for revision-specific selector eligibility and project selector-only behaviour through the effective profile.
Keep vendor snapshots unchanged when a documented legacy selector is absent.
Explicit `local_scenes` entries use catalogue `scene_id=0` and `effect_id=selector`, are marked `local_only`,
and are exposed only by profiles that explicitly admit the selector.

## Repository non-goals

These exclusions apply globally to every model, including Experimental profiles,
services, Effect Studio, queries, and recovery.  App availability or known BLE
encoding does not override them.  The repository may retain decode-only Kaitai
documentation and protocol findings for excluded features; this does not
authorise runtime control.  It does not expose:

- AI filters, including their BLE selectors, configuration, and readback;
- Wi-Fi provisioning, cloud control, or account and network setup;
- on-device timers, countdowns, or schedules; use Home Assistant automations instead;
- phone or host microphone capture, injection, or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates, for device safety;
- manufacturer-style animated scene previews; or
- camera calibration that depends on Govee Wi-Fi or cloud services.

Onboard device-microphone modes, ordinary BLE commands, and bounded multipart effect uploads remain in scope.
BLE installation direction and white balance are not excluded by the cloud camera
image-calibration non-goal; qualify each independently using exact-model evidence.
Known Wi-Fi provisioning and onboard-timer layouts belong in Kaitai documentation,
not runtime provisioning, cloud communication, timer queries, or timer writes.
Keep new excluded-feature speculative roots out of the runtime root list and
runtime imports. Unknown layouts remain documented gaps, not invented schemas.

## Validation

Before considering a contribution complete, run `make check` on the final tree and resolve any failures.  Run `make package` only when producing a distributable package.  Hassfest and HACS remain CI-enforced checks.

CI builds and verifies the runtime package, then passes that exact artifact to the hosted core checks and an independent reproducibility rebuild in parallel.
Restore generated outputs after dependency installation without overwriting checkout sources or restoring the ZIP's fixed 1980 timestamps.
Generated-output freshness verification runs in the build and reproducibility jobs; the core checks do not repeat compilation.
Browser tests run independently against source fixtures in the official Playwright image, whose version must match `@playwright/test`.
The required Check job requires core, browser and reproducibility checks to succeed.
The CI-only `make check-code` target requires verified build outputs and is not a replacement for the complete local `make check` gate.

The full Python suite uses four worker processes and combines their branch coverage.
Use `make check PYTEST_WORKERS=2` on memory-constrained machines, or `PYTEST_WORKERS=0` to investigate a serial full-suite failure.
Targeted commands such as `uv run pytest tests/test_coordinator_status.py -q` remain serial by default.

Fake devices should answer supported queries incidental to the scenario; tests for missing replies remove those responses explicitly.
Use the opt-in `virtual_clock` fixture for coordinator deadline and suppression tests that do not need real I/O.
It advances asyncio timers and coordinator monotonic timestamps together, preserving production durations and real notification parsing, waits and cancellation.
Do not patch a monotonic clock independently of absolute asyncio deadlines, or mock successful verification to avoid a timeout.
Keep filesystem/executor-backed operations and real-time lifecycle smoke tests outside virtual time.
Callbacks with the same deadline have no guaranteed order; fake radios that require ordered delivery must schedule replies in that order.

Python upgrades must keep `project.requires-python`, `.python-version`, `uv.lock`, and the Ruff and mypy Python targets aligned.  CI reads its interpreter version from `.python-version`; regenerate the lockfile with `uv lock` and validate with `make check`.

After switching branches, protocol verification can report obsolete ignored
modules.  `make clean` only knows the current runtime output list.  Remove only
the reported ignored files absent from `scripts/kaitai-runtime-outputs.txt`,
then rerun the gate.

Keep Conventional Commit merge parsing enabled in semantic-release so release-bearing merges still trigger releases when the branch commits are fixups.
Write `feat:` and `fix:` commit subjects as clear, user-facing summaries of what changed; keep implementation details in normal body paragraphs (which semantic-release omits from release notes) and use `NOTICE: <text>` or `BREAKING CHANGE: <text>` paragraphs for extra user-facing release notes.

For live qualification, distinguish optimistic entity state from fresh BLE readback.
Use `homeassistant.update_entity` when verifying state outside the command's confirmation queries.
H617A static RGB is confirmed through complete segment replies, not the colour-mode reply.

### Maintainer release-candidate qualification

Use a published RC installed through HACS for live qualification, not SSH deployment or direct file copying.
When release and live testing are authorised, follow this established route without asking the owner to choose a deployment mechanism again.

The [prerelease workflow](.github/workflows/prerelease.yml) delegates packaging and publication to the
[shared Home Assistant prerelease workflow](https://github.com/teh-hippo/common-repo-configs).
The caller pins a released provider commit by full SHA, with its release tag alongside the pin.  Review a provider release before updating that pin.
Build-only runs (`publish=false`) upload the deterministic ZIP, checksum and build metadata without creating a release.
Only the artifact manifest receives the normalised version: `7.13.1-rc.2.h6102` becomes `7.13.1rc2`.
Feature branches keep the stable source version, and prereleases never move GitHub's latest release.

1. Run the final `make check`, commit the reviewed candidate, and push its feature branch.
   Dispatch the prerelease workflow with that branch selected, its exact lowercase 40-character commit SHA as `target_sha`,
   a fresh `version` in `MAJOR.MINOR.PATCH-rc.N.SUFFIX` form, and `publish=true`.
   The SHA must be reachable from the selected branch.  Set `release_notes` to the exact maintainer-approved public notes; publishing requires non-empty notes.
   Require a successful run and verify the tag's target SHA and the package checksum.
2. Before deployment, capture the installed release and the test devices' restorable state, including hidden mode/settings when a light is off.
   If a state cannot be safely restored, resolve that before changing it.
3. Discover the integration's HACS `update` entity through Home Assistant.
   Refresh it with `homeassistant.update_entity`, then call `update.install` with the exact RC tag as `version`; do not rely on `latest_version`.
   Confirm the installed tag, then restart Home Assistant with `homeassistant.restart` to load the new Python code.
4. Wait for Home Assistant and the target config entries to load, then confirm the runtime manifest version in diagnostics matches the RC.
   HACS installation metadata alone proves downloaded files, not running code.
   Exercise the affected workflows through the normal REST/WebSocket interfaces and require fresh BLE readback rather than optimistic entity state.
5. Clean up temporary previews and restore each device's captured state even if a test fails, then verify restoration through fresh readback.
   Keep diagnostics private and bounded.  Report the exact RC, observed results and any unverified behaviour.
   Publish another exact-SHA RC for subsequent source fixes rather than hotpatching the installation or reusing a tag.
