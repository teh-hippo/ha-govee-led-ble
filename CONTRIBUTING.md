# Contributing

## Requesting support for another model

Open a support-request issue for the exact model and apply its exact SKU label (for example `H617A`, `H6199`, or `H6076`); pull requests for a specific model should carry the same SKU label.
For owner confirmations, comment on the model's confirmation child under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442) instead of opening another confirmation issue.
Include:

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
- `generated_protocol_adapter.py` connects generated structures to semantic builders and parsers; `protocol_core.py` holds the shared Kaitai roots and framing helpers, and `protocol_<grammar>.py` modules hold single-grammar codecs and wire transforms.  Handwritten protocol code is limited to semantic transforms, checksums, and transport framing.
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
  Set `profile_pact_dependent` when Pact alone changes capabilities, so runtime resolution also runs before hardware or firmware replies arrive.
  Declared `physical_ic_count` represents product geometry; `ReadDomain.PHYSICAL_IC_COUNT` (`aa 40`) measures installed geometry on the active strip and overrides declared product geometry when observed.
  Cached identity stabilises UI presentation across polls and Release-mode disconnects, while operation admission and physical writes require current-connection confirmation.
  Identity observations invalidate authorisation only when a capability depends on that field.  Background setup and polling retry a changed identity or profile once with fresh queries; command verification remains strict.
  State-readable devices default to Release mode and use Hold mode only when configured for periodic polling.
  Entry shutdown also cleans up BLE after failed setup: unsubscribe stop listeners, cancel entry-owned keep-alive work and run bounded connection cleanup.
  Recheck entry lifetime after awaited setup stages and physical writes, as well as before writes, so late operations cannot restart BLE work after shutdown.
  Connected operations allow 60 seconds per setup attempt for discovery, connection, notifications, encryption and identity; preview preflight allows two such attempts.
  Keep those setup budgets separate from shorter query, upload-acknowledgement and verification deadlines.
  Readable power does not imply observable effect activation.  A mode or selector reply confirms selection, not uploaded content, speed, or rendering.
  Music/video mode readback must not infer a saved profile from deployment history.  Preserve current saved-profile origin through power-only transitions;
  explicit native selection supersedes it only at an admitted effect-changing write.  Deployment recovery restores origin only after physical restoration succeeds.
  Upload acknowledgements and retry admission are independent of status readback.  A profile that forbids replay after an upload attempt must not reupload merely because selection readback is missing.
  DreamView member claim, disable and restoration rules: see the `coordinator_dreamview.py` module docstring.
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
3. Provision the model's confirmation issue and wire its number into the exact-SKU profile.  New candidates and speculative Kaitai schemas can then merge directly to `master` as `Experimental` once `make check` passes; no blocking prerelease gate is required.
4. Owners test the available features on actual hardware and comment on that model's confirmation issue, recording exact hardware, firmware and integration versions, successes and failures.
5. Maintainers review those observations, resolve reported failures and promote the model in code once working hardware is confirmed.

Prerelease versions are stamped only in packaged artifacts when published for targeted testing; feature branches and `master` retain the current stable source version.

### Creating model confirmation issues

Maintainers provision one canonical confirmation child per exact SKU under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442).
Check the tracker first: use an existing confirmation child rather than creating another for each owner, hardware revision, firmware version or release.
For a model without one:

1. Draft a new child with the title `<MODEL>: owner confirmations by hardware and firmware revision` and its exact SKU label.
2. Review the title and body before publishing.  State the current support status, invite reports after evaluation, and include the comment template and diagnostics/privacy instructions below.
3. Create the child under the tracker and verify its parent and SKU label.  Historical support requests and bug reports remain separate context; do not repurpose them as confirmation threads.
4. Store the new issue number in `ModelProfile.confirmation_issue` for that exact SKU before merging or releasing Experimental support.

Compatible codecs and replaced profiles must not inherit another SKU's issue.
The invariant tests require every registered Experimental model to have a valid, distinct confirmation destination.
Supported models can retain their confirmation child for later revision reports without becoming Experimental again.

The integration never creates issues, looks them up on GitHub, or changes their state.
Studio and setup use the declared issue number, so simultaneous owners all reach the same thread and add comments.

### Promoting Experimental support

Support status is declared in code, not inferred from GitHub activity or a device preference:

1. Review owner-observed behaviour for the exact model and record the tested hardware, firmware and integration versions, restoration behaviour and remaining gaps in the confirmation thread.
   Existing issues, pull requests and maintainer-owned hardware count when they identify the exact SKU and observed working controls.  Link the original evidence, retain corrections and contrary results, and leave missing versions or untested features explicit rather than inferring them.
2. Change that SKU's `ModelProfile.support_quality` to `SupportQuality.SUPPORTED` in `const.py`, including any separate revision profiles for the same SKU.  Do not change another model or a shared codec.
3. Update the README support table and the supported/experimental model expectations in `tests/test_const.py`.  Then run `make check`.
4. Ship the reviewed change in a release and update the confirmation thread's status summary with the release, original evidence links and confirmed revisions.
   Close the confirmed model's confirmation issue as completed; leave it unlocked for later revision reports and keep unresolved bug reports open.

Owners receive the new status after installing that release, restarting Home Assistant and reloading the frontend.
The native device label and Studio/setup notices follow the declared status; hiding feedback, submitting a report or closing an issue does not promote a model.
Keep the same confirmation URL available after promotion or issue closure so older installations and new revision reports still reach it.

An accepted write, a UI-only trial or another SKU's report is not hardware confirmation.
Supported means owner-confirmed hardware, not that every hardware/firmware revision has been tested; keep unreported revisions and known gaps explicit.
Keep models without exact-SKU owner confirmation Experimental, regardless of shared codecs, passing tests, successful setup alone or results obtained only through another integration or transport.
Promoting support does not promote speculative Kaitai schemas to evidence-backed schemas; those have their own capture requirements below.

## Device-owner validation

Sharing confirmations is voluntary and never unlocks controls or blocks normal use.
The template asks for exact model, hardware and firmware versions, integration version, version source, what was tried, visible successes/failures, untested features and restoration problems.
Do not infer support for an unreported revision or promote a model automatically from successful writes.

Effect Studio's Feedback action prepares a selectable report and opens the existing model issue; it does not create issues or upload anything.
Owners edit the report in their GitHub comment.  Missing versions stay unknown until supplied from an identified source such as the Govee app.
Feedback presentation uses existing observations only and must not trigger BLE queries, create Repairs or notifications, or interfere with editor work.
Known diagnostic redactions do not guarantee anonymity; owners should review downloads before attaching them publicly.
Session dismissal is per config entry and browser tab, using session storage rather than a durable user preference.
The permanent integration option is per config entry and affects all users; neither setting changes the model's native Experimental classification.
New Experimental devices receive an informational setup step with the canonical issue link before entry creation, without a feedback requirement.
Keep existing-entry reconfiguration unchanged and recheck duplicate identity after the informational step.

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
Kelvin confirmation may retry complete transitional segment snapshots within a bounded deadline, without replaying the write or changing the original sibling/brightness baseline.
H66A0 partial writes confirm plausible settled rendering, not exact Kelvin.  H1A42 and H61F5 compare their rendered palette; H61F5 retains commanded Kelvin without treating its zero aggregate register as RGB proof.
The three models round requests to 100 K with upward ties before building, presenting or verifying them.  Their direct RGB sentinel remains independent of companion conversion.
Unknown native-white intent prevents lossless preview/recovery.  A captured known-RGB layout must come from complete observations following a successful RGB write on the current subscription; failed writes, optimistic or legacy state do not qualify.
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
hand-select a subset.  The refresh tool writes each category and effect on one
line within the existing JSON schema to keep exact-SKU snapshots compact and
diffable.  Catalogue availability proves scene identity and vendor
payload data only; it does not prove transport, activation, upload, or readback
compatibility.

Review snapshot identity changes and update pinned digests and parser counts together.  Keep edge-case tests independent of whether the current vendor catalogue contains an example.

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

`generated_protocol/` is a gitignored build output.  Run `make protocol` after a fresh clone, a new worktree, or any `.ksy` change, before running `pytest` directly.

Generation canonicalises peer-schema import order in staging.  Preserve that step so identical schema inputs produce byte-identical runtime packages.

Before considering a contribution complete, run `make check` on the final tree and resolve any failures.  Run `make package` only when producing a distributable package.  Hassfest and HACS remain CI-enforced checks.

Unused code fails `make check` (vulture).  Delete it rather than keeping it "in case", and test behaviour through the real entry point rather than adding a hook only tests call.  A name that must stay although nothing references it goes in `vulture_whitelist.py`, in the group that explains why.

Frontend contract fixtures use a synthetic integration version.
Do not derive their contents from the source manifest: prerelease packaging stamps that manifest before `make package`, which must still verify the same committed fixtures.
Keep the custom-effect catalogue response complete in frontend contract fixtures so production decoding checks the aggregate model inventory against its byte budget.
The aggregate budget is separate from the individual model-catalogue limit; do not weaken unrelated JSON limits when the inventory grows.

Browser tests run independently against source fixtures in the official Playwright image, whose version must match `@playwright/test`.
CI passes the backend contract fixture from the core-check job to browser tests as an artifact.  The browser image needs no Python toolchain.
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
Fake radios compare absolute transition deadlines, not subtracted monotonic floats, so replies at the boundary remain stable across host uptimes.

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

Maintainers: the release-candidate qualification runbook is in [docs/release-candidates.md](docs/release-candidates.md).
