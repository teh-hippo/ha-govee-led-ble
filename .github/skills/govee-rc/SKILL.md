---
name: govee-rc
description: >-
  Publish a verified Govee master RC, identify impacted issues and qualify or resolve each one.
license: MIT
---

# govee-rc

Argument: an optional exact master candidate tag.
Use the [release-candidate guide](../../../docs/release-candidates.md) and [govee-resolve](../govee-resolve/SKILL.md).

1. Establish the candidate boundary.
   - Without a tag, verify exact current `master` has successful validation and ask the operator to approve `Release` with `release_type=rc`.
     Never dispatch a stable release or `force_major` from this skill.
   - With a tag, verify it is a published, immutable prerelease.
   - Wait for publication, verify the exact source SHA is included, and confirm the workflow succeeded with the packaged tag, version and checksum.
   - Stop on a failed or stale candidate; do not treat local source or an artefact as published.
2. Find the release impact range from the preceding published candidate to this candidate.
   Inspect commits, merged PRs, release notes and issue references in that range.
   Also inspect exact-SKU `confirmation_issue` links for model additions or promotions.
   Trace shared changes to affected models and operations; a missing text reference is not proof that an issue is unrelated.
   Deduplicate linked issues and report uncertain associations for operator classification.
3. Classify every impacted open issue:
   - **Needs hardware confirmation:** keep it open and prepare a short candidate reply with the exact tag, HACS installation and restart steps, the affected controls, and the result to report.
   - **Confirmed and shipped:** resolve it only when the candidate contains the complete fix or promotion and the required maintainer or owner verification already exists.
   - **Partially fixed, new problem or missing evidence:** keep it open and state the remaining gap.
   - **Already closed or unrelated:** take no public action.
4. Show every issue comment draft and every proposed close, reaction or state change to the operator for approval before publishing it.
   After approval, post or resolve exactly the approved issues and retain the evidence: issue, candidate, source SHA, verification and resulting action.
   Do not close an Experimental support request until complete owner confirmation exists and the Supported promotion has shipped.
   Maintainer-verified bugs need no reporter confirmation, comment or reaction before close.
