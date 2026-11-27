# Contributing

## Requesting support or suggesting fixes

Use one issue per exact SKU for support requests, implementation and owner verification.
Include the SKU in its title and description; point `confirmation_issue` and the README Experimental link there.
Name affected models in issue and PR descriptions.

When consolidating existing threads, retain active owner discussion; otherwise prefer the original request.
Preserve closed-thread history, link it from the survivor and update feedback links.
New Supported-model bugs and features use fresh issues, retaining historical feedback links.

Describe problems through observed behaviour and sanitised diagnostics.
Put protocol corrections in the model's `.ksy`.
Keep Bluetooth addresses, serial numbers, account details and other unique identifiers private.

## Architecture

One shared Home Assistant light core serves explicit product declarations.
Profiles own product facts, Kaitai owns wire structure, and shared runtime operations own execution.

### Shared core and product boundaries

- Kaitai schemas are the source of truth for BLE wire structure.  Generated protocol types carry wire differences into codecs; shared Python must not reconstruct or select raw structures by exact SKU.
- Exact models are expected to expose distinct product facts and wire or semantic formats.
  Keep those differences in profiles, catalogues and narrow codecs selected through declared grammars or typed semantics, never as exact-model patches in shared execution.
  Model names in declarations and codecs are not evidence of SKU-dependent shared execution.
- Common code owns behaviour that has one contract across models.
  A shared capability must mean the same thing to every caller; adjacent facts with different consequences require separate fields rather than inferred compatibility.
- Adding a new SKU should normally require only explicit product declarations, Kaitai evidence and the narrowest new codec needed to join existing shared capability paths.
  If support requires scattered exact-model branches, fix the missing shared boundary instead of treating the product as a snowflake.
- Model-specific exceptions can remain when evidence requires them.
  Trace the active declaration through preparation, transport, observation and recovery, name the preserved contract and keep the exception at its owning boundary.
- The Home Assistant integration is the public product.  Expose stable entities and controls first, then keep protocol and product details below that boundary.

### Shared behaviour and product differences

- Trace declarations, public controls, preparation, transport, observations and recovery across equivalent entry points and capability combinations.
- Follow active caller selection and precedence before comparing codecs; an available builder is not proof that a device uses it.
- Classify differences as product facts, wire formats, distinct semantics or shared defects.
  Use existing seams first; justify new ones with evidence.
- Fix shared causes at their owning layer, migrate callers and remove duplicate paths and state.
  Evidenced semantic overrides are narrow, typed and capability-selected, preserving shared boundaries and other profiles.
- Keep ordinary controls independent of optional features.
  Capabilities authorise workflows; grammars encode them.
  Preserve semantic intent through preparation.
- Effect Studio reads and direct BLE operations honour the Home Assistant primary-light entity policy.
  `read` or `control` grants Studio viewing; `control` grants that light's physical operations.
  Shared library, default and configuration mutations remain administrator-only.
- Identify entities by stable identity and declared role.
  The primary light retains its role when disabled or absent.
  Sources have independently addressable power, explicit colour modes and native attributes.
  Separate main-light modes, device-wide capabilities and wire grammars.

### Capability and protocol authority

- `const.py` contains one complete, explicit profile per exact SKU.
  Share codecs while declaring command, status and effect grammars independently.
  Cover every evidenced revision within scope.
- Each temperature-capable SKU declares its Kelvin ranges, including revision differences.
  Use Home Assistant's native temperature mode and bounds.
  Normalise requests and restoration to the effective range; retain valid native Kelvin observations.
  Companion colours are protocol data.
  White mode requires a qualified temperature for exact restoration.
- Shared designs retain authored content, identity and source metadata.
  Resolve target-local values separately, preserving other defaults.
  Qualify semantics independently of names and wire numbers.
- Keep authored catalogue references distinct from resolved target scene identities through selection, application, attribution and reload.
  Persist explicit scene selectors independently of catalogue display names; authored programmes can have no native name.
  The release contract, narrowed by the effective profile, governs support, apply projections, defaults and template resolution.
  Advertised defaults must compile within it.
  Qualify each authoring workflow independently; template identity survives readiness changes and reload.
  Represent unknown, unsupported and explicitly disabled separately.
- `tools/ble/kaitai/**/*.ksy` owns BLE wire structure and protocol documentation.
  `speculative/` holds hypotheses; other schemas require evidence.
  Generate runtime outputs and preserve unknown fields as opaque data.
  Apply evidenced compatibility policy over generated shapes; required encryption takes precedence.
- Before registering a new profile, run `uv run python tools/ble/refresh_scene_catalogues.py <SKU>`.
  Model plans and findings live in their issue or PR.

### Evidence-led model work

Use available evidence to confirm the active operation and revision; an issue, capture, starting brief or public source can provide the entry point.
Distinguish evidence strength from the conclusion, and a software comparison from hardware confirmation.
Record competing routes and the observation that would distinguish them.
Keep private references out of the repository and public discussion.
The [shared evidence method](.github/skills/govee-shared.md) covers model investigation and reporting.

### Identity qualification

- Evaluate revision prerequisites together.
  Dependent controls require complete, consistent live evidence.
  Missing identity is temporary readiness; retain safe bootstrap controls and final-write checks.
- For subscription-qualified identity, cached values serve presentation.
  Reconcile fresh markers, current-subscription advertisements and declared identity reads.
  Protocol authority lasts for its subscription, independently of scanner-cache expiry.
  Observed state retains its own lifetime.
- Reconcile expiry at operation boundaries before capturing generations; capability getters are side-effect free.
  Re-query missing control identity before client reuse and qualify bootstrap profiles before effect compilation.
- Prepare optional scene identity during scene admission.
  Scene-policy changes preserve unrelated state and revalidate dependent transfers and acknowledgements against their preparation and current authority.
- Complete preparation when the requested workflow, selector and scene are qualified, without waiting for unrelated optional identity.
- Declare optional-only revision prerequisites in `effect_identity_fields`, separately from ordinary-control identity and generations.
  Late optional replies preserve independent controls, transfers and recovery; revalidate dependent uploads when identity or authority changes.

### State, ownership and execution

- Entities adapt input and presentation; coordinators own admission, qualification, attempts and recovery.
  Ordinary controls send the first request immediately, then coalesce to the newest per control.
  Power and queued attributes share a merged stream; services, Studio and background work submit directly.
- Use complete typed requests and prepared results.
  Validate semantics and the whole operation before state-changing writes; compile once and retain revalidation metadata.
  Keep editable intent separate from wire values.
  Acquire omitted mandatory values through qualified independent observations.
- Preparation reads preserve the submitting request.
  Own only required preparation work; API identity stays background-owned until validation succeeds.
  Preview cancellation preserves owned preparation and newer requests.
- Bind work and observations to device, effective profile, layout, subscription and operation generation as applicable.
  Enter and leave task-owned contexts within device ownership.
  Revalidate at physical boundaries and invalidate knowledge with its authority.
  Newer work, observations and sessions take precedence.
- Retire field expectations when a newer owned physical attempt can change the field, including native side effects.
  Verification requires complete shapes and companion values; matching readback preserves it, contradictions revoke it.
  Separate deployment history from active attribution; reconcile live identity and observations after persistence before entity notification.

### Static appearance and effect recovery

- Ordinary effects require a complete executable static baseline before leading writes.
  Validate content, acquire readable fields under ownership and reuse that operation's observations.
  Capture intent before the first attempt; publish it at the physical mode transition.
  Models explicitly declaring retained static palette readback may acquire a cold baseline while a scene, DIY or music mode is active.
  Require fresh, complete independent colours and relative levels, plus current power and brightness, and use the declared palette restoration semantics.
  This recovers the retained static bank, not an animation frame or an unknown effect body.
  Never replace original or incomplete recovery history, or downgrade invalidated history to a newly read bank.
- Without recovery history, an exact already-resident native video selector may resume with power and brightness only.
  Require fresh independent current-subscription mode and complete applicable settings, including requested template defaults; conservatively exclude unqualified supplementary parameters.
  Recheck evidence and ownership at every physical boundary, never rewrite the mode or invent a restoration target.
  Actual selection changes and exits still require the original static baseline.
- Preserve complete appearance, including segment colours, native colour semantics and relative brightness, across effect changes and every exit path.
  Keep original appearance current until the first attempt, then recovery appearance or selector through dependent completion.
  Accepted selectors remain authoritative through activation, retry and rollback; uploads authorise payloads only.
  Requalify mode and layout by independent readback, retaining colour intent; unknown supplementary selectors remain inconclusive.
- Bind rollback to its starting observations, including source settings, before persisting progress.
  Retain incomplete targets across planned release separately from the original baseline.
  Clear them after complete readback verification; static mode alone proves only mode.
  Require a usable restoration target before any exit operation's lighting writes.
- Planned idle and polling releases may suspend historical recovery intent.
  Reuse after qualifying connection, control profile, geometry and mode.
  Compare static encoding independently of optional-effect encoding and retain its actual identity prerequisites.
  Current observations and prepared writes retain their own lifetimes.
  Unexpected loss, failed release and explicit invalidation discard recovery history.
- Preserve fully delivered write-only appearances and evidence quality, including before the first effect.
  Own cold recovery preparation and retain layout through leading attributes and restoration.
  Basic static controls can establish missing recovery state.
  Separate the original baseline from immediate-prior deployment-failure recovery.
- Live effects retain the original baseline and capability-specific independent-colour/layout requirements.
  Explicit cancel and close stop future work, then restore the original owned appearance after any active transaction reaches a known boundary.
  A newer state-changing foreground control or committed Apply takes ownership; supersession retains those completed changes instead of rolling them back.
  Saved-item selection, Save and Auto Save during Live use the same preview session; library persistence does not commit the physical appearance.
  Read-only refreshes and admission supersession do not transfer appearance ownership.
  Internal recovery uses its own prepared authority and original baseline.
  Confirm readable power-off independently; otherwise require completed delivery.
- Native static RGB authoring uses ordinary segment controls.
  Canvas starts and clears every segment to RGB black (Off); saved compositions define all logical segments as RGB intent.
  Omitted segments mean unchanged only in low-level transient paints.

### Geometry, colour and evidence

- Update geometry and derived counts together within declared capacity.
  Equivalent profile resolution preserves observations and transactions.
  Partitions cover each position exactly once, excluding separately addressed sources.
  Require geometry for operations addressing it; preserve siblings with qualified state and mappings that leave them unchanged.
  Qualify source-selection constraints with current-subscription flags before writes.
- Qualify shared temperature hints against complete current source colours, preserving explicit intent.
  Presentation inference and exact restoration have separate authority.
  Retain colour semantics at write granularity alongside complete RGB and brightness palettes, including mixed layouts.
  Reconstruct unknown native intent through evidenced declared operations.
  Recovery may retain complete delivered write-only colours and levels; Preview requires independent observations.
  Qualify each readable field independently of its write capability, and enforce dependent read authority at both physical query and subscription observation boundaries.
  Dependent reads require explicit protocol admission even when writes are unrestricted.
- Distinguish admission, preparation, physical attempt, completed delivery and independent confirmation.
  Track physical attempts explicitly and qualify observations independently of optimistic state and expired expectations.
  Write-only delivery completes after required acknowledgements.
  Missing independent readback for readable Studio deployments remains uncertain, without replay or rollback solely to obtain confirmation.
  The first upload attempt invalidates active workspace attribution for its overwritten selector, not unrelated selectors.
  Rollback and retransmission require failure evidence beyond missing readback.

### Resource ownership

- Scope state, locks and reservations to their resource; keep unrelated items independent during I/O.
  Derived compatibility views follow library generations and effective profiles.
- Cache derived results at their owning layer and invalidate on meaningful changes.
  Serialise changed observations and background writes while accepting newer edits.
  Background updates preserve focus and unsaved content; foreground operations own editor locking.

### Transport, recovery and lifecycle

- Route physical writes through common guarded transport.
  Use validated acknowledgements, transitions and completion-driven backpressure; timeouts bound failures.
  Track replies before writes, learn silence from successful subscription-local attempts and restore pacing on valid late replies.
- Resolve GATT characteristics within their owning service and use the resolved object for I/O.
- Submit multipart transfers, including injected writers, as complete prevalidated ordered transactions.
  Separate authored length from padding and preserve bytes except for requested edits.
  Bind chunks to their authorising sequence; retain typed metadata outside packet state.
  Invalidate payload knowledge at the first physical attempt; replace it after complete delivery and required acknowledgement.
  Subscription or profile invalidation completes pending waits.
- Shared batch execution and recovery operate independently of written values.
  Attribute partial failures under ownership, reconcile earlier attempts after rejection and recover affected state.
  Rollback preserves fresh observations, newer ownership and the original error, releasing reservations and tasks on cancellation.
- Preserve failure classification through wrappers.
  Connection retries require connection failures; missing verdicts, rejection, ownership and programming errors retain their outcomes.
  Completed uploads awaiting verdicts remain single transfers across subscription loss.
  Admit foreground retransmission independently of background availability.
- Initialise owners before lifecycle callbacks.
  Drain tasks, acknowledgements and retired clients through cancellation and teardown, including disconnected links.
  Bound cleanup to its owning client.

## Support status

New models merge as `Experimental` and ship through operator-published master candidates.
Reference the request in the PR; keep it open through implementation and owner testing.
After an owner confirms that exact model on hardware, set `SupportQuality.SUPPORTED` in `const.py` and update the README.
Close the request once the promotion merges and ships in a verified release.
Confirm software and owner hardware separately.

## Repository non-goals

Runtime support excludes these features for every model, including Experimental ones:

- AI filters;
- Wi-Fi provisioning, cloud control, or account and network setup;
- on-device timers, countdowns or schedules (use Home Assistant automations);
- phone or host microphone capture, or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates;
- animated scene previews; or
- camera calibration that depends on Govee Wi-Fi or cloud services.

Decode-only Kaitai documentation remains in scope.

## Development

The Makefile owns build orchestration:

| Command | Purpose |
| --- | --- |
| `make bootstrap` | Install project-pinned tools and locked Python/frontend dependencies. |
| `make protocol` | Generate protocol code for backend tests or scene refresh in a fresh checkout, and after `.ksy` changes. |
| `make fixtures` | Generate frontend contract fixtures when required. |
| `make build` | Build protocol and frontend outputs. |
| `make check-fast` | Run a broad non-hardware checkpoint: workflows, lint, generated outputs, fixtures and frontend/static contracts. |
| `make check` | Completion gate, including independent generated-output verification, full Python branch coverage and mobile WebKit. |
| `make package` | Produce a requested distributable archive. |

CI requires exact-run contract fixtures, package reproducibility and a fail-closed aggregate Check for source-bearing runs.
Semantic-release commits use the lightweight path only after exact version-only diff verification and successful validation of their parent.

- Start with `make bootstrap` in each native checkout, or use the optional dev container as a wrapper around the same target.
  Native development is the default; OS prerequisites are limited to Git, mise and the C toolchain required by native Python dependencies.
- Prefer the narrowest loop while editing: a focused pytest target, frontend `typecheck`/`test:unit` or the affected generated-output target.
  The Vite fixture loop runs with `npm --prefix frontend run dev`; it does not require a Home Assistant restart or a release candidate.
- Keep packaged Studio JavaScript compatible with Safari 15.6, including lazy chunks.
  Supply usable CSS fallbacks for newer features; current Playwright WebKit does not reproduce an older iOS engine.
- Use `make check-fast` after broader local changes and `make check` once the final tree is ready.
  Do not repeatedly run the completion gate for unchanged files or package unless a distributable is requested.
- Run independent pytest processes serially within a checkout; use the runner's workers for parallel tests.
  Use `PYTEST_WORKERS=1` to diagnose collisions, then fix resource ownership.
- Use Home Assistant's published `pytest-homeassistant` package, including its `bluetooth` extra, as the test-framework authority.
  Do not install `pytest-homeassistant-custom-component` alongside it or override pytest away from its supported version.
  Upgrade Home Assistant and the test package together.
- Prefer Core-owned fixtures and helpers for `HomeAssistant`, config entries, registries, storage, WebSocket/HTTP clients, time and Bluetooth manager state.
  Keep a local fixture only for a Govee protocol, transport, recovery, storage-port or test-environment responsibility that Core does not provide.
- Use `enable_bluetooth` with the published advertisement builders and injection helpers when scanner-manager behaviour matters.
  Keep narrow unit tests direct, and retain native Bleak/ESPHome tests when they prove backend behaviour rather than Home Assistant fixture behaviour.
- Declare fixture dependencies statically, including indirect parametrised fixtures.
  Do not call `request.getfixturevalue` for async Home Assistant fixtures from inside a running async test.
- Keep mutable storage test-local.
  The gate owns its browser server, exact build, OS-assigned port and readiness check.
  Virtual event-loop clocks belong only around simulated transport.
- When an imported editor module contract changes, invalidate asset generation in both `effect_contracts.py` and `frontend/src/contracts.ts`.
- Log handled failures by operation, model and classification while preserving browser feedback.
  Use trusted reasons or exception types and source locations; keep request bodies and identifiers private.

### Change and test design

- Group work by shared cause and observable contract, including affected callers.
  Propose independent discoveries as follow-ups with scope approval.
- Extend existing suites for distinct contracts, representative capability partitions and boundaries.
  Exercise public entry points, state and recovery with faithful boundary doubles.
  Catalogue tests cover identity, loading and protocol; byte assertions protect encoding and rewrite contracts.
- Characterise surprising behaviour against device evidence before changing it.
  Preserve genuine constraints in shared coverage and remove temporary or duplicate tests.
  Test asynchronous ordering and ownership through explicit synchronisation.
- Name the new contract, parameter partition or replayed regression introduced by each test.
  Add exact declarations and pure data to exhaustive corpora, but require a distinct observable partition for expensive execution.
- Add no Cartesian matrix axis unless each value can change the tested outcome.
  Use per-operation equivalence classes only after proving the profiles agree for every relevant admission, identity, geometry, transport and recovery input.
- Protect branch arcs, prohibited effects and targeted faults, not just aggregate line or branch percentages.
  Prove replacements without the superseded tests before deleting them.
- Establish capability limits across individual, combined and service operations and evidenced revisions.
  Protect working workflows when resolving failures or missing controls.
- Refactors preserve complete relevant public payloads and generated wire output.
  Fixes demonstrate the old failure and intended behaviour.
- Challenge both exceptions and abstractions.
  Justify special treatment, share equivalent capability paths and remove superseded code, state and tests.
  Preserve product declarations and safety boundaries.

Record contracts, partitions, evidence and blockers in a plan/PR acceptance table before editing.
Independent review covers completeness, resulting paths, callers, ownership and equivalent partitions.
Resolve coupled findings; changed inputs reopen dependent contracts, and shared invariant changes broaden review.
Follow findings and invalidated evidence to closure; standalone audits retain their scope.

New models require a complete device brief and completeness audit across evidenced revisions.
A fresh-context audit also satisfies code review when it covers implementation correctness.

Consolidate corrections, reconcile upstream at readiness and validate the final tree.
Reuse unchanged local proof after fetch/status or no-op rebase.
Relevant input changes reopen checks; rewritten commits require exact-SHA CI.
Keep generated contract fixtures incremental locally, but retain clean generation and independent verification at package and completion boundaries.
Approve public drafts before posting and track known workflow run/check IDs.

### Dependency caches

Retain dependency pins, Home Assistant verification and required native compilation.
Share compatible dependency-only caches across validation and packaging; master uses trusted default-branch caches.
Prune with `uv cache prune --ci`.
Every source-bearing run performs clean generation, verification and exact-SHA acceptance.
Only verified release metadata may reuse its validated parent.

## Releases

Keep `master` release-quality.
Python Semantic Release owns versions, release commits, tags and notes from Conventional Commits.
`feat`, `fix`, `perf`, `build` and breaking changes drive releases; documentation and maintenance alone leave versions unchanged.

| Path | Authority and result |
| --- | --- |
| Master candidate | Operator runs `gh workflow run release.yml --ref master -f release_type=rc` on validated `master`; `Release` publishes `v<version>-rc.<number>`. |
| Optional PR candidate | Operator-approved, reviewed exact-SHA hardware-test build through `Prerelease Package`, tagged `v<version>-pr-<PR number>.<candidate number>`. |
| Stable | Operator runs `gh workflow run release.yml --ref master` on current validated `master`. |

Manual `Release` defaults to stable; select `release_type=rc` for candidates.
Use [major-version selection](docs/release-publication.md#intentionally-starting-a-major-version) for explicit major releases.

Publication requires successful validation of exact current master.
After master advances, wait for its checks and retry.
Master RC and stable share a serial lock; active publication finishes before waiting replacements.
Tags and published releases remain immutable; stable publication alone moves GitHub's latest stable release.

Every release publishes a verified integration ZIP and SHA-256 checksum.
GitHub CLI uploads assets through a draft, then publishes after successful upload.
Recover failed publication at the same exact commit and tag using [release recovery](docs/release-publication.md#recovering-a-failed-publication).

Follow [release candidates](docs/release-candidates.md) for build inputs, Marketplace installation and hardware testing.
