# Contributing

## Requesting support or suggesting fixes

Request a new model with a support-request issue containing the exact SKU in its title and description.
Use one issue per exact SKU for the request, implementation and owner verification; do not create a separate confirmation issue or attach it to a parent tracker.
Set the model's `confirmation_issue` and README Experimental link to that request so the integration directs later owners to the same discussion.
Identify affected models in issue and pull request descriptions, not with device-model labels.
For a device-specific problem on a supported model, open an issue or pull request describing the behaviour you saw, with diagnostics.  Fixes are welcome as suggestions, and protocol corrections belong in the model's `.ksy` file.
Existing model threads with active owner discussion remain their feedback issue; when consolidating a request and a separate confirmation issue, keep the active discussion and prefer the original request if neither is active.
Retain discussion history on the closed issue, link it from the survivor, and update integration and README links when the feedback destination changes.
New bugs or feature requests for Supported models get fresh issues without replacing the historical model-feedback link.
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
  A genuine behavioural override must be narrow, typed and capability-selected.
  It must preserve other profiles' behaviour and use the same validation, transport and recovery boundaries.
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
- Every temperature-capable SKU declares its own Kelvin range explicitly, including evidenced revision differences; there is no default device range.
  Use Home Assistant's native colour-temperature mode and Kelvin bounds, keeping product limits independent of compatible wire grammars.
  Normalise requests and restoration writes against the effective range, but preserve valid native Kelvin observations rather than clamping them to the write limits.
  Required BLE companion colours remain protocol data, not Home Assistant RGB approximations.
  A white-mode indicator without a qualified temperature is not RGB or an exact Kelvin observation; never restore it from an unrelated retained colour.
- Give each fact one authority.
  Shared library designs retain their authored content, identity and source metadata; resolve target-local values without rewriting the design or another device's defaults.
  Qualify shared behaviour and parameter meaning independently of display names and wire numbers.
  Keep authored catalogue references separate from resolved target scene identities through selection, application, attribution and reload.
  Derive catalogue support and apply projections from the release contract, narrowed by the effective profile, rather than maintaining parallel capability flags.
  Project catalogue defaults and direct template resolution from the same effective contract; every advertised default must compile within its bounds.
  Evaluate authoring workflows independently; a native encoding for one workflow must not hide another workflow that the product supports.
  Keep structural template identities independent of transient revision readiness so defaults remain valid after persistence and reload.
  Preserve distinctions between unknown, unsupported and explicitly disabled.
- Evaluate revision prerequisites together and fail closed when required identity is missing or a prerequisite fails.
  Where identity requires subscription qualification, cached identity is presentation-only; require current-subscription evidence before authorising dependent writes.
  Reconcile fresh markers, current-subscription advertisements and declared protocol-identity reads; conflicting live evidence cannot authorise controls.
  Bind qualified protocol evidence to its live subscription, not scanner-cache age; advertisement expiry alone must not revoke it or clear independently observed state.
  Release that authority when its subscription ends, without using retained presentation identity to authorise a replacement.
  Reconcile expiry at explicit operation boundaries before capturing generations; capability getters must be side-effect free.
  Re-query missing control-profile identity before reusing a connected client and qualify restricted bootstrap profiles before effect compilation.
  Optional scene identity belongs to scene preparation and admission, not ordinary control readiness or observation lifetimes.
  Scene-policy changes preserve unrelated state; revalidate dependent transfers and pending acknowledgements against their actual preparation and current authority.
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

- Entities adapt Home Assistant inputs and presentation; the coordinator owns admission, state qualification, physical attempts and recovery.
  Ordinary entity controls send the first request immediately and coalesce later requests to the newest per control.
  A light's power and attribute requests share one control stream, merging queued attributes; services, Studio and background work bypass this coalescing.
- Use complete typed requests and prepared results, not expanding keyword lists, positional tuples, string-matched intent or private sentinels in public state.
  Validate the whole operation before its first state-changing device write, compile once, and retain the metadata required to revalidate it.
  Keep authoring intent separate from profile-prepared wire values; do not reconstruct editable content from an irreversible preparation.
  Check semantic eligibility directly rather than constructing dummy packets or encoding content merely to authorise an operation.
  Recover omitted mandatory values through qualified independent observations, not successful writes or retained cache alone.
  Preparation reads retain the submitting operation's intent; acquiring state must not invalidate that same request.
  Scope preparation ownership to the required work, not unrelated connection or persistence stages.
  Keep API identity preparation under background ownership until validation succeeds, so invalid requests cannot invalidate active previews.
  Cancelling previews inside an already-owned foreground operation must not invalidate that operation's preparation or conceal a newer foreground request.
- Bind prepared work and observations to their actual lifetime: device, effective profile, layout, subscription and operation generation as applicable.
  Capture static restoration intent before an effect operation's first state-changing attempt, including leading power, and publish it only at the physical mode transition.
  Preserve complete static appearance, including segment colours and relative brightness, through every mode-exit entry point.
  Keep the original appearance current until the first physical attempt, and the recovered appearance or selector current through dependent writes and completion.
  Keep accepted selector changes authoritative through activation, retry and rollback; uploads do not authorise a change of selector.
  An unrecognised selector in a supplementary settings reply is not a definite mode change.
  Requalify dependent mode and layout through independent readback without discarding retained colour intent.
  Bind rollback to its starting observations, including source settings it may restore, before persisting recovery progress.
  Matching readback preserves verification; a contradiction revokes it, and a complete response without the required field cannot establish it.
  Retire earlier field expectations when a newer owned physical operation can change that field, including native side effects; never retire them during admission or preparation.
  Keep historical deployment confirmation separate from current active attribution; recheck the observation and reconcile active identity before notifying entities after persistence.
  A static mode report after a partial exit is not proof of restoration; retain the incomplete target across planned release independently of the original effect baseline, and verify without repainting before clearing it on completion.
  An unavailable restoration target rejects before lighting writes; never substitute aggregate colour or an invented default.
  Enter task-owned operation contexts after acquiring device ownership, and release them before releasing that ownership.
  Revalidate at physical boundaries, and invalidate dependent knowledge when its authority changes.
  Older work must not invalidate newer preparation, restore over newer observations or mutate a replacement session.
- Admit ordinary effect selections only with a complete, executable original static baseline, before leading power, brightness, colour or effect writes.
  Validate the requested content first and acquire readable baseline fields within the owned operation; subscription freshness alone cannot exclude an unreported external change.
  Reuse observations acquired by that same operation rather than repeating reads.
  Preserve the original baseline across effect-to-effect changes and restore it on effect off, independently of scalar main-light presentation.
  Successful planned idle and polling releases may suspend historical recovery intent, never current observations or prepared writes.
  Preserve complete delivered write-only native appearances too, including before the first effect selection.
  Requalify the connection, effective control profile, installed geometry and current operating mode before reusing that history.
  Unexpected loss, failed release and explicit lifecycle invalidation still discard it.
  Keep cold recovery preparation under ownership and retain its layout context through leading attributes and restoration.
  Missing recovery state is temporary readiness, not unsupported hardware; basic static controls remain available to establish it.
  Keep this baseline distinct from deployment-failure immediate-prior recovery.
  Live effect selections retain the original static baseline with its capability-specific independent-colour/layout requirements; cancel and close stop future work without undo writes.
  Native static RGB authoring uses ordinary segment controls, not effect admission or a stationary effect encoding.
  Canvas starts and clears with explicit RGB black (Off); only low-level transient paints may omit segments to leave them unchanged.
  Saved RGB compositions must define every logical segment; they do not capture brightness, power or native white intent.
  Preserve historical evidence quality across effect transitions rather than promoting delivered colours to observed state.
  Internal recovery consumes its own prepared authority rather than admitting another selection or publishing a replacement baseline.
  Final power-off requires independent confirmation where readable and completed delivery otherwise.
- Update physical geometry and derived logical counts together against declared product capacity.
  Equivalent profile resolution preserves observations and transactions.
  Segment partitions must cover each position exactly once and exclude separately addressed sources.
  Require geometry only for operations that address it; preserve siblings only with qualified state and mappings that leave them unchanged.
  Enforce declared source-selection constraints using current-subscription flags before writes.
- Shared colour-temperature hints are not independent source readback.
  Qualify them against complete, current source colours without overriding explicit intent.
  Keep presentation inference distinct from exact restoration intent.
  Preserve colour semantics at the granularity of the supported writes, independently of the complete RGB and brightness palette.
  Mixed sources and mixed segments are not incomplete state, and a main-light colour projection must never replace their recovery snapshot.
  Reconstruct unknown intent only through an evidenced, declared operation; do not infer native emitter semantics from matching RGB alone.
  Ordinary recovery may retain fully delivered, explicit write-only colours and levels without labelling them observed or filling gaps with defaults.
  Preview still requires qualified independent observations.
- Distinguish admission, preparation, physical attempt, completed delivery and independent confirmation.
  An executed guard is not a physical attempt; optimistic state and expired expectations are not fresh observations.
  Where no independent readback exists, successful delivery is completed, not confirmed or failed; required acknowledgements must still succeed.
  Missing confirmation alone never justifies blind rollback or retransmission.
  Verification must compare complete shapes and companion values, not a matching subset.
- Scope mutable state, locks and reservations to the resource they protect.
  Derived compatibility views follow library generations and effective profiles, not independently maintained SKU filters.
  Background capability updates revalidate dependent work without discarding authoring focus or unsaved content.
  Keep unrelated devices and items independent; do not retain collection-wide locks during device I/O when only one item needs a reservation.
  Cache derived results at their owning layer, invalidate on meaningful changes, and avoid repeated parsing, serialisation, whole-history rebuilding or persistence for unchanged observations.
  Background persistence must preserve authoring focus and accept newer edits while serialising writes; reserve editor locking for foreground operations.

### Transport, recovery and lifecycle

- Route every physical write through the common guarded transport.
  Prefer validated acknowledgements, explicit state transitions and completion-driven backpressure; timeouts bound failure, not normal operation.
  Arm reply tracking before writing, learn silent commands only from successful attempts on the current subscription, and restore pacing when a valid late reply arrives.
  Never add feature-specific sleeps or acknowledgement polling.
- Resolve GATT characteristics within their owning service and use the resolved object for I/O; UUIDs reused by other services must not redirect an operation.
- Submit multipart transfers as complete, prevalidated, ordered transactions, including injected writers.
  Keep authored payload length independent of transport-only padding; preserve retained body bytes except for explicitly requested edits.
  Bind every chunk to its authorising sequence and retain typed transfer metadata outside packet state.
  Invalidate retained payload knowledge at the first physical attempt; install a replacement only after complete delivery and any required acknowledgement.
  Subscription or profile invalidation must explicitly complete pending waits.
- Keep shared batch execution and recovery independent of the value being written.
  Attribute partial failure while holding operation ownership, reconcile actual earlier attempts when later work is rejected, and never replay a batch as recovery.
  Rollback preserves fresh observations and newer ownership, retains the original error and handles cancellation without leaking reservations or tasks.
- Preserve transport-failure classification through wrappers without converting protocol rejection, ownership failures or programming errors into retries.
  An absent upload verdict is an unconfirmed transfer, not a failed connection; it must not spend a connection retry.
  Losing a subscription while a completed upload awaits its verdict must not replay the transfer or replace the original failure.
  Background availability handling must not silently enable foreground retransmission.
- Initialise owners before registering lifecycle callbacks.
  Track and drain tasks, acknowledgements and retired native clients through cancellation and teardown, even when the link already reports disconnected.
  Cleanup must remain bounded and must not touch a replacement client.

## Support status

New models merge to `master` as `Experimental` and ship through the existing master-candidate release path.
Reference the request in the implementation PR without automatic issue-closing keywords; merging or publishing Experimental support does not close it.
An owner confirms working hardware in the same issue, and a maintainer then sets `SupportQuality.SUPPORTED` in `const.py` and updates the README table.
Keep the issue open until that promotion has merged and shipped in a verified release.
Without hardware confirmation, leave both the support status Experimental and the issue open so later owners can contribute.
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
Use `make check-fast` for iteration: it prepares dependencies, generated outputs and contract fixtures before static and frontend contract checks.
It is not a completion gate; `make check` also runs independent generated-output verification, full Python tests with branch coverage and mobile WebKit.
CI generates verified exact-run contract fixtures after Build, then runs Core and Browser concurrently; independent Package reproducibility and workflow lint remain required by the fail-closed Check job.
Run independent pytest processes serially within one checkout because generated outputs and coverage files still share the checkout.
Keep mutable test storage local to each test and browser servers owned by the gate, with OS-assigned ports and explicit readiness.
The full gate owns its browser test server; do not qualify an exact build through an unrelated or reused preview server.
Use `PYTEST_WORKERS=1` only to diagnose collisions; fix resource ownership rather than making serial execution the normal gate.
Keep virtual event-loop clocks out of real HTTP/WebSocket tests; use them only around simulated transport work.
Invalidate the editor asset generation in both `effect_contracts.py` and `frontend/src/contracts.ts` when its imported module contract changes, not just the backend compiler version.
Log handled backend failures with their operation, model and failure classification without changing browser feedback.
Keep request bodies, unique identifiers and arbitrary exception text out of diagnostic logs; use trusted reasons or exception types and source locations instead.

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
- Review both the exception and the proposed abstraction.
  Justify any remaining special treatment with evidence, check that equivalent capability combinations use the same core, and remove superseded branches, adapters, state and tests.
  Prefer a smaller implementation, but do not trade away explicit product declarations or safety boundaries to meet a line-count target.

Before editing, record required observable contracts, affected capability partitions, evidence and unresolved blockers in a small plan/PR acceptance table.
Independent review challenges that scope's completeness and the complete resulting paths, including callers, ownership boundaries and equivalent partitions.
Resolve every supported coupled finding; changed requirements or relevant inputs reopen acceptance across the contract's dependency reach, not just edited lines.
Broaden review when a shared invariant changes.
Only demonstrably independent findings become proposed follow-ups requiring scope approval; uncertainty is not a reason to exclude a blocker.
New models still need the complete device brief and completeness audit across evidenced revisions.
An independent completeness audit can also satisfy fresh-context code review only if it covers both completeness and implementation correctness.
Further passes follow supported findings and invalidated evidence, not an arbitrary audit limit or a new broad discovery pass by default.
Standalone requested audits retain their requested scope.
Software acceptance remains separate from owner hardware confirmation and does not establish that no bugs remain.

Consolidate related corrections before another full gate or push, reconcile upstream at readiness and validate the resulting tree.
Do not repeat unchanged local proof for fetch/status or a proven no-op rebase.
Source, dependency, toolchain and other relevant input changes reopen the corresponding checks; rewritten commits still require their exact-SHA CI.
Keep public drafts subject to operator approval and wait on known run/check IDs rather than repeatedly rediscovering workflow state.

### Dependency caches

Locked native dependencies may need compilation on Python 3.15; do not remove Home Assistant verification or override dependency pins to obtain wheels.
Validation and packaging share the `uv-v2` runner-image OS, architecture, resolved Python version and SOABI cache prefix.
Exact keys include root Python/dependency declarations; compatible fallback lets project-version-only changes reuse built wheels while uv selects locked, ABI-compatible packages.
Master packaging adds a release suffix to retain Semantic Release's own dependency builds without isolating it from compatible validation wheels.
Cache only dependency downloads/builds and prune with `uv cache prune --ci`, never virtual environments, generated outputs, archives or passing checks.
GitHub's workflow-ref scope limits master publication to trusted default-branch caches; selected-branch builds cannot populate that cache.
A matching key is not authentication, and a cache hit never replaces clean generation, verification or exact-SHA acceptance.
Cold builds and genuine dependency/interpreter changes still require compilation.

## Releases

Keep `master` release-quality.
There are three publication paths:

- **Master candidates:** after a release-bearing change merges and `Validate` succeeds on current `master`, `Release` automatically publishes the upcoming version as `v<version>-rc.<number>`.
  Python Semantic Release calculates versions and release notes from Conventional Commits; `feat`, `fix`, `perf`, `build` and breaking changes drive releases.
  Documentation or maintenance alone does not force a candidate.
  To request the same candidate path manually, select `release_type=rc` in `Release`; the manual default remains stable and neither path forces a maintenance-only version.
  For an explicitly requested major version, select `force_major=true`; this uses Semantic Release's standard override and cumulative notes from the last stable.
  Continue later candidates normally, and repeat that selection when publishing the intended major as stable.
  Publication rejects a calculated version below current master; see [major-version selection](docs/release-candidates.md#intentionally-starting-a-major-version).
- **Optional PR candidates:** request a reviewed, exact-SHA build when hardware testing is needed before merge.
  `Prerelease Package` publishes `v<version>-pr-<PR number>.<candidate number>` tags, for example `v7.40.1-pr-145.1`.
  The master release checkout excludes these preview tags locally so they cannot affect master numbering or release notes; remote tags remain untouched.
  See [release candidates](docs/release-candidates.md) for publication and testing.
- **Stable releases:** the operator decides when current validated `master` is ready.
  Manually run `Release` on `master` (`gh workflow run release.yml --ref master`).
  Python Semantic Release creates the stable version, release commit, tag and notes; do not promote by editing a prerelease checkbox or choosing a version by hand.
  Stable and explicitly forced-major checkouts also exclude master-candidate tag refs locally, so their generated notes cover changes since the previous stable release.
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
