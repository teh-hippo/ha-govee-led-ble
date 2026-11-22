---
name: govee-fix
description: >-
  Fix a user-reported Govee BLE problem. Give it an issue number: it compares how we handle the
  reported behaviour with the device evidence, fixes the owning shared path while preserving justified
  product differences, and hands the reporter a release candidate to test.
license: MIT
---

# govee-fix

Argument: an issue number.
Read `.github/skills/govee-shared.md` first.

Goal: find why the reported behaviour differs from how Govee drives that model, and fix it.

Resolve the exact SKU and revision from the issue, comments and diagnostics.
Compare model declarations and runtime behaviour with device evidence.
Report hardware, environment or vendor-firmware causes when established.

Task list:

1. Report the divergence and trace complete control and recovery paths across equivalent capability combinations.
   Classify it under the shared design workflow.
2. Fix the owning layer, migrate affected callers and protect the corrected contract in existing shared tests.
   Preserve evidenced product differences under canonical architecture.
3. Reconcile upstream, close independent acceptance review, commit, pass `make check` and open the PR.
   Reference the issue and keep it open for reporter confirmation.
4. Use an approved optional PR candidate for pre-merge hardware testing, or merge the green PR and use its automatic master candidate.
   Verify the workflow and assets under `docs/release-candidates.md`.
5. Show the operator a short reply draft and post after approval:
   > This should fix `<the problem>`.
   > Install `<RC tag>` through HACS, restart Home Assistant and confirm whether it works.
   `govee-resolve` handles closure after reporter confirmation.
