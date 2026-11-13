---
name: govee-fix
description: >-
  Fix a user-reported Govee BLE problem. Give it an issue number: it compares how we handle the
  reported behaviour with the device evidence, fixes the owning shared path while preserving justified
  product differences, and hands the reporter a release candidate to test.
license: MIT
---

# govee-fix

Argument: an issue number.  Read `.github/skills/govee-shared.md` first.

Goal: find why the reported behaviour differs from how Govee drives that model, and fix it.

You have: the issue, its comments and diagnostics; the model's Kaitai, profile and catalogues; the device evidence.  Resolve the exact SKU and revision from the issue.  If the cause is outside our code (hardware, environment, Govee firmware), say so instead of fixing something speculative.

Task list:

1. Report the divergence: what the evidence shows, what we do, where.
   Trace it through the complete control and recovery path, and compare equivalent operations and capability combinations.
   Determine whether identity merely exposes a shared defect or actually selects evidenced device semantics.
2. Follow the shared design workflow and fix the root cause at its owning layer.
   Do not add a device check, copied handler, optional-feature prerequisite or local retry to make only the reporter's path pass.
   Keep necessary differences declarative where possible.
   Otherwise justify a narrow, typed, capability-selected override that preserves the shared validation, transport and recovery boundaries.
   Migrate affected callers.
   Protect the corrected contract in existing shared tests; characterise genuine device constraints without creating a test suite or permanent workaround for each report.
3. Review, commit, `make check`, PR (references the issue without an automatic closing keyword).
4. Follow `CONTRIBUTING.md` release policy.  If reporter testing is needed before merge, obtain approval for an optional PR candidate (`docs/release-candidates.md`).  Otherwise, merge the green PR and use its automatic master candidate.  Verify the published workflow and assets; do not publish stable.
5. Draft a short reply for the reporter and show it to the operator; post it only once they approve:
   > This should fix `<the problem>`. Install `<RC tag>` through HACS, restart Home Assistant and confirm whether it works.
6. Stop.  `govee-resolve` closes the issue once the reporter confirms.
