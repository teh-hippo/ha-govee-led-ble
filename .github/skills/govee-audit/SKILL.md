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
   Treat owner confirmation as a baseline for working behaviour; reconcile later reports against the audited version.
   Open a claim ledger using the mandatory fields and authority classes in the [shared evidence method](../govee-shared.md#maintain-the-evidence-ledger).
   Record unknown revision fields explicitly and keep unlike revision tuples separate.
2. Compare active paths with evidence and [shared boundaries](../../../CONTRIBUTING.md#shared-core-and-product-boundaries).
   Compare the evidenced operations with what Home Assistant actually offers on that revision.
   Trace the reported choices, and a representative of each other in-scope route, from the public selector or service through admission, delivery and applicable recovery.
   In each ledger row, record the inspected public entry points, any route absence or blocking point, and, only when a route exists, its terminal proven handoff.
   Distinguish software reachability from acknowledgement, physical acceptance and readback.
   Distinguish justified product facts and codecs from SKU-dependent decisions in shared execution, including indirect capability coupling.
   Distinguish KSY field layout from valid product values, and exact-SKU evidence from shared-codec inference.
   Treat generated output only as a mirror: verify its freshness with `make verify-protocol-fresh` before relying on it, and retain Kaitai or the attributable capture/observation as the underlying authority.
   Before confirming a defect, follow the active guard or owner, including any replacement path, and show why it does not uphold the contract.
   Leave behaviour unchecked when that path cannot be established.
3. Check available prerequisites before running the smallest tests that exercise the contract and revision boundaries.
   Expand for shared callers or uncovered risks; a test need not name the SKU to be relevant.
   In a read-only audit, use non-mutating checks with available outputs; a missing build prerequisite limits the check, not the device.
   Live BLE operation is qualification work owned by the [release-candidate runbook](../../../docs/release-candidates.md), not an audit prerequisite or coverage gap.
   Reserve `make check` for change acceptance.
4. Report only material user-visible defects, missing supported behaviour or evidence conflicts, grouped by owning cause and impact.
   Perform a final ledger-to-report cross-check before assigning severity.
   Every finding must trace to a ledger row with matching operation, SKU, complete revision provenance, inspected public entry points and route result, authority class, freshness result and disposition.
   Require a terminal handoff only when a route exists.
   Remove unledgered claims and mark unreconciled revision, route or generated-output claims unchecked rather than inferring a finding.
   Lead with a positive pass when the requested scope is established and there are no findings.
   If a material software path remains unchecked, name it and the missing evidence rather than passing the whole scope.
   If there are findings, present them in a Markdown table with coloured severity glyphs: `🔴 High`, `🟠 Medium` and `🟡 Low`.
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
