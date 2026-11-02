---
name: govee-fix
description: >-
  Investigate a Govee BLE issue or PR report. Give it an issue number: it works out the model, finds
  the specific failure and proposes fixes across Kaitai, profiles and shared runtime code.
license: MIT
---

# govee-fix

Argument: an issue or PR number (`/govee-fix #511`), optionally with replies or diagnostics.  Read `.github/skills/govee-shared.md` first.

1. **Report:** read the issue/PR body, comments, corrections, linked changes and diagnostics.  Record the action, expected/actual result, working controls and latest outcome with source links.  Resolve the exact SKU and revisions from it.
2. **Model:** read the model's `.ksy`, `ModelProfile`, catalogue and the evidence folder's starting points for it.
3. **Trace:** follow the shared trace to the first divergence.  Identify the responsible KSY, profile, adapter or shared runtime path, a regression that would expose it, and the neighbouring callers and revisions it touches.
4. **Fixes:** propose the correction and any evidenced neighbouring fixes.  Audit the surface around the failure; hand wider gaps to `govee-audit` as a follow-up.
5. **Plan:** write the four-section plan with owner acceptance checks for the reported failure and distinct regressions.
