---
name: govee-audit
description: >-
  Audit delivered Govee BLE behaviour, missing support and special treatment against device evidence.
license: MIT
---

# govee-audit

Argument: one or more SKUs, an issue or a concern.
Use the [shared evidence method](../govee-shared.md).

1. Set the scope: whole device across evidenced revisions, or the requested operation and affected contracts.
   Severity filters findings, not which capability domains a whole-device audit considers.
   Treat `SupportQuality.SUPPORTED` and its confirmation issue as a supported owner-qualification baseline, not as a prompt to reinterpret ordinary safety annotations as new defects.
2. Compare active paths with evidence and [shared boundaries](../../../CONTRIBUTING.md#shared-core-and-product-boundaries).
   Distinguish justified product facts and codecs from SKU-dependent decisions in shared execution, including indirect capability coupling.
   Before confirming a defect, follow the active guard or owner, including any replacement path, and show why it does not uphold the contract.
   Leave behaviour unchecked when that path cannot be established.
3. Check available prerequisites before running the smallest tests that exercise the contract and revision boundaries.
   Expand for shared callers or uncovered risks; a test need not name the SKU to be relevant.
   In a read-only audit, use non-mutating checks with available outputs.
   Live BLE operation is qualification work owned by the [release-candidate runbook](../../../docs/release-candidates.md), not an audit prerequisite or coverage gap.
   Reserve `make check` for change acceptance.
4. Report only material user-visible defects, missing supported behaviour or evidence conflicts, grouped by owning cause and impact.
   Mention justified product differences only when needed to explain a finding.
   State the user-visible consequence in plain language before protocol terminology.
   Keep evidence annotations, synthetic coverage and runtime guardrails outside the findings list unless they conflict with the delivered or owner-confirmed behaviour.
   Distinguish a software defect, missing support and an evidence conflict.
   Propose a next discriminating check only for an actual conflict.
   Omit generic method and coverage caveats when they do not affect a finding.
   Never report unperformed live BLE operation or physical qualification as an audit finding, gap, severity or limitation.
   Do not report the checkout SHA unless it is needed to identify a reproducible or release-specific result.

Standalone audits report findings without editing files or evidence notes.
In `govee-add`, close and recheck coupled findings before acceptance.
