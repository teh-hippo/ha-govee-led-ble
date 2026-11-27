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
   Merge the fix to validated `master`.
   Invoke `govee-rc` after merge to publish and verify the candidate, classify affected issues and prepare their approved replies.
   An [approved PR candidate](../../../docs/release-publication.md#building-an-optional-pr-candidate) remains available for pre-merge hardware testing.
4. Keep the report open when hardware confirmation is still needed; close it only through the verified classification in `govee-rc`.
