# Contributing

## Requesting support or suggesting fixes

Request a new model with a support-request issue and the exact SKU label; pull requests for a specific model carry the same label.
For a device-specific problem on a supported model, open an issue or pull request describing the behaviour you saw, with diagnostics.  Fixes are welcome as suggestions, and protocol corrections belong in the model's `.ksy` file.
Owner confirmations go on the model's confirmation child under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442), not in new issues.
Do not post Bluetooth addresses, serial numbers, account details or other unique identifiers.

## Architecture

Provide one shared Home Assistant light core, repeated through explicit capability declarations.
Keep real product differences without turning each product into a separate implementation.

### Shared behaviour and product differences

- Trace the complete affected path before editing: capability declaration, public control, preparation, transport, observation and recovery.
  Compare equivalent operations across entry points and capability combinations, not just the reporting device.
- Classify each difference as a product fact, a wire-format difference, a genuinely different operation or a defect in the shared mechanism.
  Put facts in profiles/catalogues, wire structure in Kaitai, and execution in the shared runtime.
  An identity check, device-named helper, duplicated handler or new feature flag needs an evidenced reason that those existing seams cannot express.
- Fix a shared cause at its owning layer and migrate affected callers rather than adding an exception beside the symptom.
  Prefer deleting duplicate paths and redundant state; do not introduce a general framework, growing switch or override hook for every device.
  A genuine behavioural override must be narrow, typed, capability-selected and use the same validation, transport and recovery boundaries.
- Keep ordinary controls independent of optional features and transport encodings.
  Shared grammar does not grant capabilities, and shared transport does not make distinct semantic workflows interchangeable.
  Preserve semantic intent through preparation rather than reconstructing it from packets later.
- Identify entities by stable identity and declared role, not enumeration order, enabled-entity counts or display names.
  A source cannot substitute for an absent or disabled primary light.
  Declare sources only for independently addressable power controls, with explicit colour modes and native attributes.
  Keep the main light's colour modes separate from device-wide colour capabilities; presentation must not select a wire grammar.

### Capability and protocol authority

- `const.py` holds one complete, explicit profile per exact SKU; compatible products may share codecs but never inherit a whole profile.
  Select command, status and effect grammars independently.
  Aim for complete in-scope support on every evidenced revision, not discovery or capability flags alone.
- Give each fact one authority.
  Derive catalogue support and apply projections from the release contract, narrowed by the effective profile, rather than maintaining parallel capability flags.
  Preserve distinctions between unknown, unsupported and explicitly disabled.
- Evaluate revision prerequisites together and fail closed when required identity is missing or a prerequisite fails.
  Where identity requires subscription qualification, cached identity is presentation-only; require current-subscription evidence before authorising dependent writes.
  Reconcile fresh markers, current-subscription advertisements and declared protocol-identity reads; conflicting live evidence cannot authorise controls.
  Bind qualified protocol evidence to its live subscription, not scanner-cache age; advertisement expiry alone must not revoke it or clear independently observed state.
  Release that authority when its subscription ends, without using retained presentation identity to authorise a replacement.
  Reconcile expiry at explicit operation boundaries before capturing generations; capability getters must be side-effect free.
  Re-query missing profile identity before reusing a connected client and qualify restricted bootstrap profiles before effect compilation.
  Missing identity is temporary readiness, not evidence that the hardware lacks a workflow; preserve safe bootstrap controls and final-write authorisation.
- `tools/ble/kaitai/**/*.ksy` is the only source of BLE wire structure and protocol documentation.
  Files under `speculative/` are unconfirmed hypotheses; the rest are evidence-backed.
  Generated outputs are never edited.
  Keep offsets, command literals and packet enums out of entities and coordinators; preserve unknown fields without assuming zero padding or reinterpreting opaque bytes.
- Compatibility exceptions belong to evidenced product policy over a generated wire shape, not permissive parsing fallbacks.
  Advertised or established encryption requirements always take precedence.
- A new model needs its scene catalogue: run `uv run python tools/ble/refresh_scene_catalogues.py <SKU>` before registering its profile.  A workflow keeps existing catalogues current.
- Plans and findings for a model live in its issue or pull request, not in `docs/`.

### State, ownership and execution

- Prepare effect recovery from fresh required observations before checking restorable source state.
  Query only the native settings needed by the operation, and distinguish unsafe restoration from a Bluetooth connection failure.
- Entities adapt Home Assistant inputs and presentation; the coordinator owns admission, state qualification, physical attempts and recovery.
  Ordinary entity controls send the first request immediately and coalesce later requests to the newest per control.
  A light's power and attribute requests share one control stream, merging queued attributes; services, Studio and background work bypass this coalescing.
- Use complete typed requests and prepared results, not expanding keyword lists, positional tuples, string-matched intent or private sentinels in public state.
  Validate the whole operation before its first state-changing device write, compile once, and retain the metadata required to revalidate it.
  Check semantic eligibility directly rather than constructing dummy packets or encoding content merely to authorise an operation.
  Recover omitted mandatory values through qualified independent observations, not successful writes or retained cache alone.
  Preparation reads retain the submitting operation's intent; acquiring state must not invalidate that same request.
  Scope preparation ownership to the required work, not unrelated connection or persistence stages.
  Keep API identity preparation under background ownership until validation succeeds, so invalid requests cannot invalidate active previews.
- Bind prepared work and observations to their actual lifetime: device, effective profile, layout, subscription and operation generation as applicable.
  Revalidate at physical boundaries, and invalidate dependent knowledge when its authority changes.
  Older work must not invalidate newer preparation, restore over newer observations or mutate a replacement session.
- Update physical geometry and derived logical counts together against declared product capacity.
  Equivalent profile resolution preserves observations and transactions.
  Segment partitions must cover each position exactly once and exclude separately addressed sources.
  Require geometry only for operations that address it; preserve siblings only with qualified state and mappings that leave them unchanged.
  Enforce declared source-selection constraints using current-subscription flags before writes.
- Distinguish admission, preparation, physical attempt, completed delivery and independent confirmation.
  An executed guard is not a physical attempt; optimistic state and expired expectations are not fresh observations.
  Where no independent readback exists, successful delivery is completed, not confirmed or failed; required acknowledgements must still succeed.
  Missing confirmation alone never justifies blind rollback or retransmission.
  Verification must compare complete shapes and companion values, not a matching subset.
- Scope mutable state, locks and reservations to the resource they protect.
  Keep unrelated devices and items independent; do not retain collection-wide locks during device I/O when only one item needs a reservation.
  Cache derived results at their owning layer, invalidate on meaningful changes, and avoid repeated parsing, serialisation, whole-history rebuilding or persistence for unchanged observations.

### Transport, recovery and lifecycle

- Route every physical write through the common guarded transport.
  Prefer validated acknowledgements, explicit state transitions and completion-driven backpressure; timeouts bound failure, not normal operation.
  Arm reply tracking before writing, learn silent commands only from successful attempts on the current subscription, and restore pacing when a valid late reply arrives.
  Never add feature-specific sleeps or acknowledgement polling.
- Submit multipart transfers as complete, prevalidated, ordered transactions, including injected writers.
  Bind every chunk to its authorising sequence and retain typed transfer metadata outside packet state.
  Invalidate retained payload knowledge at the first physical attempt; install a replacement only after complete delivery and any required acknowledgement.
  Subscription or profile invalidation must explicitly complete pending waits.
- Keep shared batch execution and recovery independent of the value being written.
  Attribute partial failure while holding operation ownership, reconcile actual earlier attempts when later work is rejected, and never replay a batch as recovery.
  Rollback preserves fresh observations and newer ownership, retains the original error and handles cancellation without leaking reservations or tasks.
- Preserve transport-failure classification through wrappers without converting protocol rejection, ownership failures or programming errors into retries.
  Background availability handling must not silently enable foreground retransmission.
- Initialise owners before registering lifecycle callbacks.
  Track and drain tasks, acknowledgements and retired native clients through cancellation and teardown, even when the link already reports disconnected.
  Cleanup must remain bounded and must not touch a replacement client.

## Support status

New models merge as `Experimental`.  An owner confirms working hardware in the model's confirmation issue, and a maintainer then sets `SupportQuality.SUPPORTED` in `const.py` and updates the README table.
An accepted write or another SKU's report is not confirmation.

## Repository non-goals

These apply to every model, including Experimental ones.  The repository does not expose:

- AI filters;
- Wi-Fi provisioning, cloud control, or account and network setup;
- on-device timers, countdowns or schedules (use Home Assistant automations);
- phone or host microphone capture, or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates;
- animated scene previews; or
- camera calibration that depends on Govee Wi-Fi or cloud services.

Decode-only Kaitai documentation of these is fine; runtime control is not.

## Development

Run `make protocol` after a fresh clone, a new worktree or any `.ksy` change, and `make check` before finishing.
Keep virtual event-loop clocks out of real HTTP/WebSocket tests; use them only around simulated transport work.

### Change and test design

- Organise work by shared root cause and observable contract, not one implementation or test module per device or reported incident.
  A correct shared fix includes affected callers; unrelated discoveries remain follow-ups.
- Extend existing contract suites with representative capability partitions and boundary conditions.
  Prove the intended behaviour and safety invariant through the normal entry point, including relevant state and recovery effects.
  Avoid assertions about helper layout or duplicated constants, and keep test doubles faithful to public boundary contracts.
  Validate mutable catalogues through identity, loading and protocol behaviour, not whole-file hashes or incidental inventory counts.
  Keep exact-byte expectations only where they protect an encoding or rewrite contract.
- Characterise surprising device behaviour before changing it, distinguishing an evidenced device constraint from an integration bug.
  Preserve meaningful characterisation in shared coverage, then remove temporary or duplicate tests.
  Use explicit synchronisation to test asynchronous ordering and ownership rather than timing guesses.
- A failed command or absent detail-UI control does not establish an unsupported capability.
  Before removing advertised support, reconcile equivalent individual, combined and service operations across evidenced revisions, and protect the working public workflow rather than the proposed restriction.
- For refactors, compare complete relevant public payloads and generated wire output, not selected fields alone.
  For fixes, demonstrate the old failure and intended new behaviour without blessing the defect as a compatibility requirement.
  Report software evidence separately from hardware observations; an accepted write or optimistic UI is not physical confirmation.
- Retain bounded, redacted failure-time context for control verification and recovery decisions.
  Later state or packet-history changes must not replace the evidence explaining the failure.
  Diagnostic export is passive; do not query devices, retain private payloads or upload automatically.
- Review both the exception and the proposed abstraction.
  Justify any remaining special treatment with evidence, check that equivalent capability combinations use the same core, and remove superseded branches, adapters, state and tests.
  Prefer a smaller implementation, but do not trade away explicit product declarations or safety boundaries to meet a line-count target.

## Releases

Keep `master` release-quality.
There are three publication paths:

- **Master candidates:** after a release-bearing change merges and `Validate` succeeds on current `master`, `Release` automatically publishes the upcoming version as `v<version>-rc.<number>`.
  Python Semantic Release calculates versions and release notes from Conventional Commits; `feat`, `fix`, `perf`, `build` and breaking changes drive releases.
  Documentation or maintenance alone does not force a candidate.
  To request the same candidate path manually, select `release_type=rc` in `Release`; the manual default remains stable and neither path forces a maintenance-only version.
- **Optional PR candidates:** request a reviewed, exact-SHA build when hardware testing is needed before merge.
  `Prerelease Package` publishes `v<version>-pr-<PR number>.<candidate number>` tags, for example `v7.40.1-pr-145.1`.
  The master release checkout excludes these preview tags locally so they cannot affect master numbering or release notes; remote tags remain untouched.
  See [release candidates](docs/release-candidates.md) for publication and testing.
- **Stable releases:** the operator decides when current validated `master` is ready.
  Manually run `Release` on `master` (`gh workflow run release.yml --ref master`).
  Python Semantic Release creates the stable version, release commit, tag and notes; do not promote by editing a prerelease checkbox or choosing a version by hand.
  The stable checkout also excludes master-candidate tag refs locally, so its normal generated notes cover changes since the previous stable release.
  Automatic candidates retain those refs for native RC numbering; all remote tags remain untouched.

Each PR branch and each master publication type has its own concurrency group.
New requests replace older waiting requests only within the same group; active publication finishes.
Master RC and stable requests cannot cancel each other, but share a serial publication lock because both update master versions and tags.
Both require successful validation of the exact current master commit.
If master advances or its validation is incomplete, publication fails safely; wait for its checks and retry the manual action if needed.
Release commits do not recursively publish candidates.
Previous candidate tags and releases remain immutable history, with the newest master candidate available for testing.
Only stable publication moves GitHub's latest stable release.
No moving `latest` Git tag is required or maintained.

Marketplace users can select a candidate explicitly from the download/redownload dialog's version list without enabling prerelease updates.
Open Marketplace under **Settings > Marketplace** and use the integration's existing `update` entity for exact-version installation.
Keep prerelease updates disabled for stable-only update prompts; enabling them opts into both master and PR candidates.
Publishing a candidate does not opt users into that channel or install it automatically.

Every release carries the verified integration ZIP and SHA-256 checksum.
Semantic Release owns master versions, release commits, tags and notes but defers GitHub release creation.
After packaging and verification, GitHub CLI stages a draft while uploading assets and publishes only once those uploads succeed.
Failed publication may leave a tag or draft, not a deliberately published assetless release.
Retry only against the same exact commit; never move an existing tag or overwrite a published release.
See [release recovery](docs/release-candidates.md#recovering-a-failed-publication) for exact-tag recovery without creating another version.
Merging a model does not imply hardware confirmation or promote it from Experimental.
