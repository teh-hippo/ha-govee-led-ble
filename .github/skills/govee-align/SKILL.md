---
name: govee-align
description: >-
  Investigate Govee BLE models and issue reports during planning or implementation.
  Use hardware and protocol evidence to build concrete plans and guide fixes across Kaitai,
  profiles and shared runtime code. Accept optional models, issue/PR references, diagnostics,
  packets or conversational context. Also use for model audits and compatibility PR reviews.
license: MIT
---

# govee-align

Start from the supplied context: `/govee-align H6076`, `/govee-align #476`, `/govee-align H6199 #293`, or a request to investigate supplied replies.
Neither a model nor an issue argument is mandatory.  Resolve exact SKUs from attributable evidence; clarify missing or conflicting identity rather than guessing.

## Boundaries

- Follow `CONTRIBUTING.md` for architecture and excluded features.  Target full in-scope support across hardware and firmware revisions: enable every defensible capability backed by exact-model evidence or speculative Kaitai, keep only disproven or unsafe paths disabled, and preserve unknowns rather than inventing facts.
  Audit the full in-scope feature/revision surface, prioritising the reported failure.  Missing owner qualification alone does not withhold defensible candidates.
- Include evidenced neighbouring fixes.  Ask whether major gaps belong in the current issue/PR or a follow-up, and before materially changing the implementation approach.
  Keep deferred findings visible; delivery scope and audit coverage are separate.
- Planning, investigation and PR review are read-only: write session artifacts, not tracked files; do not run mutating generators or `make check`.
  Implementation uses a dedicated worktree when other work is active.  Invocation alone authorises neither implementation nor publication.
- Before protocol research, locate the main clone via `git rev-parse --path-format=absolute --git-common-dir`.
  Read `.reference-material/README.md` in that clone's parent and follow its confidentiality, lookup and LSP instructions.
- Research local evidence first, then targeted authoritative sources for unresolved questions, including transport failures.
  Batch searches and file slices; reuse settled findings after checking source version, checkout and owner context.
  Use `python3` for stdlib JSON/ZIP inspection.  Discover paths rather than inventing per-model `docs/` files.

## 1. Investigate while planning, not later

Perform the available intake, causal trace and audit below **now**, then construct the plan from their findings.
Do not substitute implementation todos such as "run govee-align", "inspect the packets" or "audit the model".
Use the four-section structure of `.github/PULL_REQUEST_TEMPLATE.md`:

1. **Request and known context:** Reproduction, expected/actual behaviour, identities, versions and transport environment.
2. **Research findings:** Causal evidence, packet/semantic differences, contrary evidence, audit coverage and unresolved explanations.
3. **Candidate support scope:** Proposed correction, neighbouring fixes, preserved behaviour and major-gap scope decisions.
4. **Model-specific changes and owner checks:** Affected files/shared entry points, each intended change and its evidence, distinct regressions and owner acceptance checks.

Defer only checks requiring unavailable evidence, implementation or hardware access; state the dependency and next discriminating check.
Keep planned checks distinct from performed checks.  If no correction is justified, report competing explanations instead of inventing one.
During implementation, read the plan and evidence ledger before editing; revisit changed assumptions and unexamined paths, not settled discovery.
First engagement during implementation still performs the investigation.  Reconcile changed decisions with the plan before modifying the affected path.

## 2. Establish the report's causal path

Read the issue/PR body, relevant comments, corrections, linked changes and available diagnostics.
Treat proposed causes and workarounds as hypotheses.  Keep owners, revisions, environments and reported versus checkout versions separate.
Record the action, expected/actual result, working controls and latest outcome with source links.
Without a specific report, begin the model audit rather than requiring an issue or inventing a failure.

Read the model's `.ksy` schemas first (`tools/ble/kaitai/`; `speculative/` holds unconfirmed hypotheses): they are the protocol documentation, and a wire fix belongs there.
Trace connection/subscription -> identity admission -> request construction -> framing/transformation -> physical write -> replies -> parsing -> state -> verification.
Identify the last successful stage and first evidenced divergence; a service error does not prove a malformed command.
Compare observed TX/RX with current generated output and decoded semantics at the same protocol layer:

- Retain source/version, direction, revision, sequence and timing.  Distinguish captured, reconstructed and builder-generated frames.
- Separate wrong bytes/routing from transport failure, unanswered queries, transitional readback and incorrect confirmation expectations.
  Accepted writes, visible rendering, fresh observations and optimistic state are not interchangeable.
- Locate the responsible KSY/profile/adapter/shared runtime path and a regression exposing its defect; check neighbouring callers and revision outcomes.
  Do not weaken confirmation, add retries or copy another SKU's fix without evidence.

If generated outputs are unavailable in read-only mode, inspect schemas/builders and record the pending comparison rather than running mutating generators.

## 3. Complete the model and revision audit

Maintain a concise inventory across existing `.ksy`, `const.py`, exact-SKU scene/effect catalogues and shared adapter, coordinator and entity paths.
Map `(pact_type, pact_code, hardware, firmware, subordinate_20/21)` to capabilities independently.
Check product IDs/remapping, BLE names, encryption, physical/installed/logical geometry, white emitters and power limits against attributable hardware/public evidence.
Separate Pact-safe baseline capabilities from those needing confirmed versions; reference routing is a candidate, not hardware proof.

For each feature, trace admission, bounds/defaults, body, transport, activation, ACKs, observations and recovery.  Lookup anchors, not coverage limits:

| Surface | Check |
| --- | --- |
| Power, brightness | Register bounds/rescaling (`brightness_wire_range`), clamping and non-zero readback. |
| RGB, Kelvin, segments | Selectors, bounds, direct/companion RGB, mask width/grouping, whole versus partial writes; fresh configured geometry before masks. |
| Scenes | Exact-SKU catalogue, selector width/eligibility, body routing, selector-only versus upload activation, speed metadata/defaults. |
| Music | Selectors/mode IDs, parameter bounds, companion bodies, upload ordering, ACK/retry policy and activation. |
| DIY, Workshop | Body/family allowlists, rate/palette/layer bounds, upload ACKs, slot safety and restoration. |
| Settings, video, DreamView | Control eligibility, boolean/enum semantics, query/write behaviour, subordinate gates and group capacity. |

Catalogue type, body family and wire subtype are independent.  Establish upload ACKs separately from status readback; query silence proves neither ACK policy nor cause.
Keep wire structure/codebooks in Kaitai, speculative unknowns opaque, and product capabilities in exact-SKU profiles.
Flag handwritten offsets/command literals/fallback codebooks, model branches and static profiles bypassing effective `device_profile()`.
Check `MODEL_EFFECT_CATALOGUES` and `RELEASE_CAPABILITY_CONTRACT` where affected.
Verify named fields -> observations -> sibling preservation -> persisted recovery -> generated writes -> fresh verification.
Classify relevant fields as applied, preserved, decode-only or unknown.

## 4. Verify and hand off

- **Read-only:** Run targeted pytest only for a specific frame/decode hypothesis with compatible outputs already available.
  Do not run generation/invariant/fixture sweeps on an unmodified checkout merely to claim an audit.
- **Implementation:** For wire changes, run `make protocol verify-protocol` and add attributable direct-byte regressions to `tests/test_kaitai_protocol.py`.
  Add new runtime-distinct `device_profile()` cases to `_QUALIFIED_CONTEXTS` in `tests/test_profile_wire_invariants.py`.
  Use neighbouring runtime tests for timing/state/recovery fixes; verify the reproduction, siblings and relevant revisions.  Regenerate affected fixtures and pass `make check`.
- **Review:** Use independent review when required by the task/delivery workflow, challenging causal evidence, revision assumptions, Kaitai ownership and regressions.
  Pass citations and the ledger; do not ask the reviewer to re-invoke the skill or repeat discovery.
- **Report:** Separate issue-specific conclusions from the full audit.  Distinguish unexamined, investigated-but-unresolved and not-hardware-qualified paths.
  Claim alignment only when coverage is complete; report only checks actually performed.
- **Ledger:** Keep evidence, attributable frames, paths, current decisions, contrary/superseded findings and deferred checks in `<session_folder>/files/align-<model>.md`.
  Use an issue-based filename until identity is resolved.  Link it from the plan rather than maintaining competing decisions.
- **Delivery:** Include independent review, `make check`, draft PR/comment approval, an exact-SKU-labelled PR, passing CI and rebase merge to `master`.
  Link an issue when applicable; use `Fixes #<issue>` only when resolved.  These steps neither replace planning research nor authorise publication.
