# Release candidates

Install and test the exact published candidate that contains the change.
See [release policy](../CONTRIBUTING.md#releases) for release channels.

## Installing and qualifying a candidate

1. Confirm the target Home Assistant instance, approved actions and device revisions.
   Capture the running version and a restorable device baseline, including saved mode and settings when the light is off.
   Use the HA dev runbook for local hardware setup, ownership and cleanup.
2. Refresh the integration in **Settings > Marketplace** and select the exact tag in the download/redownload selector.
   For automated installation, call `update.install` with that tag as `version`.
   The prerelease preference changes update prompts, not exact-version selection.
3. Restart Home Assistant when authorised.
   Verify the installed tag and the manifest version in diagnostics after restart.
   If restart is deferred, report the installed and running versions separately.
4. Exercise the affected workflows.
   Require fresh device readback where available, not optimistic state.
   For write-only paths, record completed delivery or acknowledgement and any independent visible observation separately.
5. Restore device state even after a failed check and verify it by available independent observation.
   If the baseline is not restorable, stop before changing it.
   Report the exact running version, revision, checks, blocked or unverified items, and cleanup result.
   Keep diagnostics private.

## Master candidates

When operator-approved, dispatch `Release` with `release_type=rc` on validated `master` to publish `v<version>-rc.<number>`.
Verify the merged source is included, the `Release` workflow succeeded, and the published ZIP, packaged version and checksum agree.
Documentation-only changes do not require a new candidate.

Use `gh workflow run release.yml --ref master -f release_type=rc`.
Manual dispatch defaults to stable.
For an [optional PR candidate](release-publication.md#building-an-optional-pr-candidate), [major release](release-publication.md#intentionally-starting-a-major-version) or [failed publication](release-publication.md#recovering-a-failed-publication), use the specialist procedure.
