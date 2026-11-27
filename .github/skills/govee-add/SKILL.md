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
   Ask the operator whether to publish a [master candidate](../../../docs/release-candidates.md#master-candidates).
   If approved, dispatch `Release` with `release_type=rc` on validated master, verify the candidate contains the merge and keep the issue open.
   If declined, report that the merge is not yet published, keep the issue open and stop.
6. With an available candidate, show the operator the requester reply before posting.
   Give the exact candidate, installation and restart instructions, and ask for revision, controls tested, visible results and untested areas.
