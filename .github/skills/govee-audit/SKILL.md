---
name: govee-audit
description: >-
  Audit delivered Govee BLE support against the device evidence. Give it a SKU, an issue or a concern
  in plain words: it builds the device brief and reports behavioural gaps, unjustified device-specific
  handling and the shared design problems behind them.
license: MIT
---

# govee-audit

Argument: free-form: one or more SKUs, an issue, or a concern.  Read `.github/skills/govee-shared.md` first.

Goal: identify behavioural gaps and unjustified special treatment across every evidenced hardware/firmware revision.

Build the device brief, then compare it with our Kaitai, profile, catalogues and complete runtime paths.
Run the delivered tests first; investigate failures and distinguish code defects from unavailable tooling or pre-existing environmental failures.
To generate our bytes without touching the checkout, build a scratch copy.
Also list capabilities we do not implement that are not non-goals, and revisions we gate off on purpose (label those as policy).

## Audit special treatment

- Trace where identity affects behaviour, including indirect grammar checks, capability overrides, catalogue filters, defaults, fallback paths and device-named helpers.
  Follow callers and recovery paths; a search for the SKU alone is not an audit.
- For each difference, determine whether it is an explicit product declaration, an evidenced wire or semantic distinction, or compensation for a shared design flaw.
  Look for duplicated authority, repeated execution paths, optional-feature coupling and state owned at the wrong layer using `CONTRIBUTING.md` as the review standard.
- Compare equivalent capability combinations and entry points.
  Ask whether expressing the same capability on another device would require copying code, and whether a shared correction would remove the exception.
  Do not propose profile inheritance, broader capability grants or a universal handler merely to eliminate visible differences.
- Challenge suspected findings against the evidence and current guards.
  Legitimate declarations and necessary overrides are not defects; a different coding preference or a line-count reduction alone is insufficient.

## Report

Group supported findings by root cause and rank them by user impact and maintenance risk, not by occurrence count.
For each, give the observed behaviour or structural problem, the evidence, affected contracts/revisions, why existing safeguards are insufficient, and the layer that should own it.
Include a mitigation direction and the shared invariant it must preserve, not a custom issue or test prescription for every occurrence.
Record justified special treatment separately so later work does not remove it without evidence.

Mark items only hardware can settle, uncertainty, intentional policy and possible non-goals.
End with what you compared and what you did not.
Private references go in the evidence folder's notes, not in the report or anything published.

Run on its own, the audit is a report: the operator decides per item whether to raise an issue or fix it now.  When `govee-add` runs it, `govee-add` fixes the findings.
