---
name: govee-fix
description: >-
  Diagnose a reported Govee BLE issue, fix the owning contract and hand the reporter a verified candidate.
license: MIT
---

# govee-fix

Argument: an issue number or an exact SKU with an identifiable report.
Use the [shared evidence method](../govee-shared.md).

1. Reproduce or characterise each outstanding symptom from its public entry point, using the reporter's revision, starting state, named choices and action sequence.
   When settings affect the result, use the owner's effective options, including those retained on upgrade.
   If unknown, compare plausible saved options with fresh defaults and keep the diagnosis conditional.
   For a regression, compare the same sequence on the last known working and first reported failing versions where available.
   If the unchanged code passes the reproduction, reconcile its setup with the report before treating it as proof.
   If no integration defect is established, report the cause or the evidence needed to distinguish it.
2. Correct the owning layer and replay the original sequence to the intended outcome.  Preserve working controls and evidenced revision differences.
   Run a focused `govee-audit` on the affected operation and equivalent callers.  Resolve downstream blockers on that path; report separate symptoms still open.
3. Follow [change acceptance](../../../CONTRIBUTING.md#change-and-test-design).
   Ask the operator whether to publish a [master candidate](../../../docs/release-candidates.md#master-candidates) after merge.
   If approved, dispatch `Release` with `release_type=rc` on validated master; an [approved PR candidate](../../../docs/release-publication.md#building-an-optional-pr-candidate) remains available for pre-merge hardware testing.
   Verify any approved candidate contains the fix and keep the issue open for confirmation.
   If publication is declined, report that the fix is merged but not yet published, keep the issue open and stop.
4. With an available candidate, show the operator a short reply draft before posting.
   Give the exact candidate, installation and restart instructions, and the original actions and expected results for owner confirmation.
