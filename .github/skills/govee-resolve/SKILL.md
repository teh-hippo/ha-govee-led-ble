---
name: govee-resolve
description: >-
  Close out Govee work once users confirm it. Give it a SKU, a confirmation issue or a bug issue: it
  promotes owner-confirmed models from Experimental to Supported, and closes bugs whose fix is
  released and confirmed.
license: MIT
---

# govee-resolve

Argument: a SKU, a confirmation issue or a bug issue (`/govee-resolve H6117`, `/govee-resolve #511`).  Read `.github/skills/govee-shared.md` first.

Goal: close what users have confirmed.  No coding beyond the support-status change.  Confirm every action with the operator before taking it.

- **Experimental model:** promote it if an owner reported it working without issues on its confirmation issue.  Open a PR that sets `support_quality=SupportQuality.SUPPORTED` in `const.py`, changes the README row to `✅ Supported`, updates `tests/test_const.py`, and references the confirmation issue.  When green, merge it, thumbs-up the confirming comment and close the confirmation issue.
- **Bug report:** if the fix is merged to `master`, released, and the reporter confirmed it works, thumbs-up their comment and close the issue.  Merge the fix's PR first if it is still open and green.
- **Anything else** (partial confirmation, new problems, no reply yet): summarise where it stands and ask the operator.
