---
name: govee-fix
description: >-
  Diagnose a reported Govee BLE issue, fix the owning contract and hand the reporter a verified candidate.
license: MIT
---

# govee-fix

Argument: an issue number.
Use the [shared evidence method](../govee-shared.md).

1. Resolve the reported SKU, revision, running version and operation from the issue and available diagnostics.
   Reproduce or characterise the divergence and distinguish integration, hardware, firmware and environment causes.
   If no integration defect is established, report the cause or the evidence needed to distinguish it.
2. Correct the owning layer, preserve evidenced model differences and test the affected contract across equivalent callers and revisions.
3. Follow [change acceptance](../../../CONTRIBUTING.md#change-and-test-design).
   Use the [master candidate](../../../docs/release-candidates.md#master-candidates) after merge, or an [approved PR candidate](../../../docs/release-publication.md#building-an-optional-pr-candidate) for pre-merge hardware testing.
   Verify the candidate contains the fix and keep the issue open for confirmation.
4. Show the operator a short reply draft before posting.
   Give the exact candidate, installation and restart instructions, and ask whether the reported behaviour is fixed.
