---
name: govee-fix
description: >-
  Fix a user-reported Govee BLE problem. Give it an issue number: it compares how we handle the
  reported behaviour with the device evidence, fixes the difference, and hands the reporter a release
  candidate to test.
license: MIT
---

# govee-fix

Argument: an issue number (`/govee-fix #511`).  Read `.github/skills/govee-shared.md` first.

Goal: find why the reported behaviour differs from how Govee drives that model, and fix it.

You have: the issue, its comments and diagnostics; the model's Kaitai, profile and catalogues; the device evidence.  Resolve the exact SKU and revision from the issue.  If the cause is outside our code (hardware, environment, Govee firmware), say so instead of fixing something speculative.

Task list:

1. Report the divergence: what the evidence shows, what we do, where.
2. Fix it, with a regression test.
3. Review, commit, `make check`, PR (`Fixes #<issue>`).
4. Build a release candidate (`docs/release-candidates.md`).
5. Draft a short reply for the reporter and show it to the operator; post it only once they approve:
   > Thanks for the report. Could you install `<RC tag>` and let me know whether `<the problem>` is fixed?
6. Stop.  `govee-resolve` closes the issue once the reporter confirms.
