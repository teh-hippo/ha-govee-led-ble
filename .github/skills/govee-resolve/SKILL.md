---
name: govee-resolve
description: >-
  Close out Govee work once users confirm it. Give it a SKU, a model-support request or a bug issue: it
  promotes owner-confirmed models from Experimental to Supported, and closes bugs whose fix is
  released and confirmed.
license: MIT
---

# govee-resolve

Argument: a SKU, support request, existing model-feedback issue or bug issue.
Examples: `/govee-resolve H6117`, `/govee-resolve #511`.
Read `.github/skills/govee-shared.md` first.

Goal: close confirmed work.
Code changes are limited to support status and its dependent README/tests.
Obtain operator approval before each action.

- **Experimental model:** require owner confirmation of complete working support on the `confirmation_issue` thread.
  Use the original request for new support and retain existing active feedback threads.
  PR: set `support_quality=SupportQuality.SUPPORTED`, update the README to `✅ Supported` and adjust existing tests.
  Reference the issue and keep it open until the green PR merges and the promotion ships in a verified automatic master candidate.
  Then thumbs-up the confirming comment and close that issue.
- **Bug:** once the fix is merged, released and reporter-confirmed, thumbs-up the comment and close the issue.
  Merge an open green fix PR first.
- **Partial confirmation, new problems or missing replies:** summarise the status for an operator decision.
