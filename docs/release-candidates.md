# Release-candidate qualification

Use a published RC installed through HACS for live qualification, not SSH deployment or direct file copying.
When release and live testing are authorised, follow this established route without asking the owner to choose a deployment mechanism again.

The [prerelease workflow](../.github/workflows/prerelease.yml) delegates packaging and publication to the
[shared Home Assistant prerelease workflow](https://github.com/teh-hippo/common-repo-configs).
The caller pins a released provider commit by full SHA, with its release tag alongside the pin.  Review a provider release before updating that pin.
Build-only runs (`publish=false`) upload the deterministic ZIP, checksum and build metadata without creating a release.
Only the artifact manifest receives the normalised version: `7.13.1-rc.2.h6102` becomes `7.13.1rc2`.
Feature branches keep the stable source version, and prereleases never move GitHub's latest release.

1. Run the final `make check`, commit the reviewed candidate, and push its feature branch.
   Dispatch the prerelease workflow with that branch selected, its exact lowercase 40-character commit SHA as `target_sha`,
   a fresh `version` in `MAJOR.MINOR.PATCH-rc.N.SUFFIX` form, and `publish=true`.
   The SHA must be reachable from the selected branch.  Set `release_notes` to the exact maintainer-approved public notes; publishing requires non-empty notes.
   Require a successful run and verify the tag's target SHA and the package checksum.
2. Before deployment, capture the installed release and the test devices' restorable state, including hidden mode/settings when a light is off.
   If a state cannot be safely restored, resolve that before changing it.
3. Discover the integration's HACS `update` entity through Home Assistant.
   Refresh it with `homeassistant.update_entity`, then call `update.install` with the exact RC tag as `version`; do not rely on `latest_version`.
   Confirm the installed tag, then restart Home Assistant with `homeassistant.restart` to load the new Python code.
4. Wait for Home Assistant and the target config entries to load, then confirm the runtime manifest version in diagnostics matches the RC.
   HACS installation metadata alone proves downloaded files, not running code.
   Exercise the affected workflows through the normal REST/WebSocket interfaces and require fresh BLE readback rather than optimistic entity state.
5. Clean up temporary previews and restore each device's captured state even if a test fails, then verify restoration through fresh readback.
   Keep diagnostics private and bounded.  Report the exact RC, observed results and any unverified behaviour.
   Publish another exact-SHA RC for subsequent source fixes rather than hotpatching the installation or reusing a tag.
