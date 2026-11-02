---
name: govee-audit
description: >-
  Audit an existing Govee BLE model for ways its support may be wrong - a model-specific review
  with no known issue. Give it a SKU; it returns a gap list across Kaitai, profile and runtime paths.
license: MIT
---

# govee-audit

Argument: a SKU (`/govee-audit H617A`), or several.  Read `.github/skills/govee-shared.md` first.  No issue is needed; this is for model audits, compatibility PR reviews and suspected unknown problems.

1. **Inventory:** assemble the model's guide in one pass: `.ksy`, `ModelProfile`, catalogue, tests, evidence-folder entry points and any open issues or confirmation-thread reports.
2. **Audit:** work through the shared surface table and field checks for every revision, comparing the profile against the evidence and the schemas.  Include the profile-versus-`device_profile()` and handwritten-literal checks.
3. **Report:** list each gap with its evidence, the affected revisions, severity and a proposed check or fix.  Separate unexamined, investigated-but-unresolved and not-hardware-qualified paths.  Suggest a release candidate where only hardware can settle a gap.
