---
name: govee-resolve
description: >-
  Promote owner-confirmed Experimental support or close a shipped, verified Govee bug.
license: MIT
---

# govee-resolve

Argument: an exact SKU, support request, existing feedback thread or bug issue.
Inspect the issue and release evidence first; open device evidence only if needed to resolve a discrepancy.
Obtain operator approval before each mutating action.

- **Experimental model:** require owner confirmation of complete working support on its `confirmation_issue` thread.
  Update `SupportQuality.SUPPORTED`, the README row and dependent existing tests.
  Follow [change acceptance](../../../CONTRIBUTING.md#change-and-test-design).
  After the promotion ships in a verified candidate, react to the confirming comment and close the issue.
- **Bug:** confirm the fix is merged and shipped, and the maintainer or operator verifies it.
  An open fix PR must merge and ship first.
  Maintainer-verified bugs need no extra reporter confirmation, comment, reaction or proof.
- **Partial confirmation or new problems:** report the remaining gap and stop for an operator decision.
