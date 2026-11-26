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
2. Compare active paths with evidence and [shared boundaries](../../../CONTRIBUTING.md#shared-core-and-product-boundaries).
   Distinguish justified product facts and codecs from SKU-dependent decisions in shared execution, including indirect capability coupling.
   Before confirming a defect, follow the active guard or owner, including any replacement path, and show why it does not uphold the contract.
   Leave behaviour unchecked when that path cannot be established.
3. Check available prerequisites before running the smallest tests that exercise the contract and revision boundaries.
   Expand for shared callers or uncovered risks; a test need not name the SKU to be relevant.
   In a read-only audit, use non-mutating checks with available outputs; report static-only coverage or unavailable comparisons explicitly.
   Reserve `make check` for change acceptance.
4. Report findings by owning cause and impact, justified differences, coverage and unchecked areas.
   Distinguish software evidence from hardware qualification and propose the next discriminating check for conflicts.

Standalone audits report findings without editing files or evidence notes.
In `govee-add`, close and recheck coupled findings before acceptance.
