---
name: govee-add
description: >-
  Plan support for a brand-new Govee BLE model. Give it a SKU: it researches the device and
  specifies the full candidate - profile entry, Kaitai, catalogue, confirmation issue and README row.
license: MIT
---

# govee-add

Argument: a SKU (`/govee-add H6076`), optionally with an issue, frames or owner replies.  Read `.github/skills/govee-shared.md` first.

1. **Identity:** confirm the exact SKU, BLE name prefix, product identifier, Pact and IC count from the evidence folder and the request.  Check related models as clues, not proof.
2. **Research:** what the evidence folder says the model does, public sources, related projects and supplied material.  Review contributed protocol files rather than accepting them as authoritative.
3. **Candidate:** specify the broadest support that can be modelled without fabricating facts: the `ModelProfile` entry (capabilities, grammars, geometry, `confirmation_issue`), the exact-model `.ksy` (in `speculative/` without device evidence), the `ModelEffectCatalogue`, and the scene catalogue (run the refresh tool before registering the profile).  Models merge as Experimental.
4. **Housekeeping:** the confirmation child under the owner-confirmation tracker, the README table row, the SKU label, and the invariant-test cases the profile needs.
5. **Plan:** the four-section plan, listing each capability's evidence, the owner checks that would promote it to Supported, and anything disproven, unsafe or non-goal.
