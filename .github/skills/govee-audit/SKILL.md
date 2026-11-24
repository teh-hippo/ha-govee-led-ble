---
name: govee-audit
description: >-
  Audit delivered Govee BLE support against the device evidence. Give it a SKU, an issue or a concern
  in plain words: it builds the device brief and reports behavioural gaps, unjustified device-specific
  handling and the shared design problems behind them.
license: MIT
---

# govee-audit

Argument: one or more SKUs, an issue or a concern.
Read `.github/skills/govee-shared.md` first.

Goal: identify behavioural gaps and unjustified special treatment across every evidenced hardware/firmware revision.

Read the evidence workspace README and exact-SKU starting brief before repository-wide discovery.
Reuse an existing brief rather than rediscovering it; build or update it when absent or stale.
Build the revision-aware device brief and compare it with Kaitai, profiles, catalogues and complete runtime paths.
Run the exact-SKU selectors and directly affected shared contract tests first.
For an exact-SKU audit, use the repository search to identify relevant test files, then select the SKU/revision cases; do not run every test in those files indiscriminately.
Expand to shared suites only where the traced path is shared or the finding invalidates a broader contract.
Classify failures as defects, missing tools or existing environment problems.
Generate comparison bytes in a scratch copy.
Include unimplemented in-scope capabilities and deliberately gated revisions, labelled as policy.
Stop once the brief, each suspected finding and every unresolved hardware question are classified.
Do not run `make check` for a read-only audit; reserve it for code-changing workflows.

## Audit special treatment

- Trace where identity affects behaviour, including indirect grammar checks, capability overrides, catalogue filters, defaults, fallback paths and device-named helpers.
  Follow callers and recovery paths.
- For each difference, determine whether it is an explicit product declaration, an evidenced wire or semantic distinction, or compensation for a shared design flaw.
  Review authority, execution, optional-feature coupling and state ownership against `CONTRIBUTING.md`.
- Compare equivalent capability combinations and entry points.
  Determine whether a shared correction removes an exception while preserving explicit product contracts.
- Challenge suspected findings against the evidence and current guards.
  Findings require a demonstrated behavioural or structural problem.
- Treat evidence conflicts and unqualified candidate paths as uncertainty or policy, not confirmed defects.
  If implementation follows one credible path, explain that choice and preserve the alternative in the brief.

## Report

Group findings by root cause and rank by user impact and maintenance risk.
Give each finding's behaviour, evidence, affected contracts/revisions, inadequate safeguards, owning layer and mitigation direction.
Name the shared invariant to preserve and record justified special treatment separately.

Mark each conclusion as **Captured**, **Exact route**, **Shared route**, **Public reference**, **Conflict**, **Inference** or **Policy/non-goal**.
List confirmed defects separately from hardware questions, uncertainty, policy and possible non-goals.
End with comparison coverage and unchecked areas.
Keep private references in evidence notes.

Standalone audits report findings for operator decisions.
Within `govee-add`, close coupled findings and re-review invalidated contracts under `CONTRIBUTING.md`, preserving complete device scope.
