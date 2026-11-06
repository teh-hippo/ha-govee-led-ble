---
name: govee-audit
description: >-
  Audit delivered Govee BLE support against the device evidence. Give it a SKU, an issue or a concern
  in plain words: it builds the device brief and reports every way our support differs from what the
  device can do and how Govee drives it.
license: MIT
---

# govee-audit

Argument: free-form: one or more SKUs, an issue, or a concern (`/govee-audit H617A`, `/govee-audit H6199 music feels wrong`).  Read `.github/skills/govee-shared.md` first.

Goal: every difference between what we deliver and what the device can do, for every hardware/firmware revision.

Build the device brief, then compare it with our Kaitai, profile, catalogues and runtime paths.  Run the delivered tests first; failures are findings.  To generate our bytes without touching the checkout, build a scratch copy.  Also list capabilities we do not implement that are not non-goals, and revisions we gate off on purpose (label those as policy).

Output: the differences, one by one, ranked by user impact, each with what the evidence shows, what we do, the affected revisions, and how much it matters.  Mark items only hardware can settle and items that may be non-goals.  End with what you compared and what you did not.  Private references go in the evidence folder's notes, not in the report or anything published.

Run on its own, the audit is a report: the operator decides per item whether to raise an issue or fix it now.  When `govee-add` runs it, `govee-add` fixes the findings.
