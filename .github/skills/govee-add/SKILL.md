---
name: govee-add
description: >-
  Add complete Experimental support for an exact Govee BLE SKU and ship a candidate for owner testing.
license: MIT
---

# govee-add

Argument: a SKU and, if available, its support request.
Use the [shared evidence method](../govee-shared.md).

1. Use one exact-SKU support request for implementation and owner verification.
   Reuse or consolidate existing threads under [contributor policy](../../../CONTRIBUTING.md#requesting-support-or-suggesting-fixes); use the [request template](../../ISSUE_TEMPLATE/model-support.md) when none exists.
2. Build a revision-aware brief, classify the whole device and map every evidenced in-scope capability to its owning declaration, codec or shared operation.
   Keep conflicting routes and owner checks explicit.
3. Cover evidenced discovery prefixes in `manifest.json`, declare the Experimental profile and its `confirmation_issue`, and add the applicable effect and scene catalogues.
   Refresh scenes before registering the profile; link the README row to the request.
   Register new Kaitai roots and outputs as needed and use existing suites for distinct contracts.
4. Run `govee-audit` against the result.
   Resolve coupled findings; a fresh audit that checks implementation correctness can also satisfy independent acceptance review.
5. Follow [change acceptance](../../../CONTRIBUTING.md#change-and-test-design), open a PR referencing the request and merge using the documented rebase-only policy.
   Invoke `govee-rc` after merge to publish and verify the candidate, classify affected issues and prepare their approved replies.
6. Keep the request open for owner confirmation of the exact revision, controls tested, visible results and untested areas.
