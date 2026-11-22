# Release candidates

A release candidate (RC) is a prerelease for hardware testing.
Follow the [release policy](../CONTRIBUTING.md#releases) and install published candidates through Marketplace.
Stable releases retain GitHub's latest-stable designation.

## Selecting a candidate in Marketplace

Open **Settings > Marketplace**.
Select the exact published tag in the integration's download/redownload version selector.
Keep prerelease updates disabled for stable-only prompts, or enable them for both master and PR candidates.
Exact-version installation works with either preference.

## Master candidates

Use the automatic candidate containing the release-bearing merge.
Python Semantic Release calculates `v<version>-rc.<number>` and updates source versions and the lockfile.
Maintenance-only changes leave the version unchanged.
If automatic publication did not run, request the validated-master path with `gh workflow run release.yml --ref master -f release_type=rc`.
Manual dispatch defaults to stable; select `rc` explicitly.
Recover an existing failed tag or draft with the same-tag procedure below.
Wait for `Release` completion and verify the ZIP and checksum before sharing.

### Intentionally starting a major version

Select `force_major=true` for an operator-requested major version.
For example, `gh workflow run release.yml --ref master -f release_type=rc -f force_major=true` uses Python Semantic Release's standard `--major` option.
Notes cover all changes since the last stable.
Subsequent automatic candidates continue normal RC numbering.

When that candidate is ready for stable, select `release_type=stable` and `force_major=true` again.
Repeat the override because ordinary stable calculation can select a lower version.
The workflow rejects downgrades and existing forced versions.
Recover failed publication at its existing immutable tag.

## Building an optional PR candidate

Push the reviewed commit after `make check`, obtain approval for publication and public notes, then dispatch **Prerelease Package** on the branch.
The branch requires an open same-repository PR targeting `master`.

| Input | Meaning |
| --- | --- |
| `publish` | Required: `true` publishes the tag/prerelease; `false` uploads package, checksum and metadata as a run artefact. |
| `target_sha` | Defaults to branch head; must belong to the selected branch. |
| `version` | Defaults to the current manifest prerelease's base version, or the next patch after a stable manifest, with `-pr-<PR number>.<candidate number>`; explicit values must identify that PR as a prerelease. |
| `release_notes` | Defaults to a generic candidate note. |
| `cache_dependencies` | Defaults to `true`; an approved controlled cold-build comparison may select `false`. |

For example, manifest `8.0.0-rc.30` keeps the PR base at `8.0.0`, while stable `7.40.0` advances it to `7.40.1`.
Example tag: `v8.0.0-pr-145.1`.
Numbers advance from existing PR tags; retrying the latest candidate's exact commit reuses its version.
Build-only runs leave numbers available.
PR preview numbering is independent of stable version calculation.
Compare cold/warm builds at the same SHA and version using archive bytes, checksums and compilation logs.
Download build-only artefacts with `gh run download <run id>`.

Existing published tags remain unchanged.
Marketplace includes both master and PR candidates when prerelease updates are enabled; this numbering rule does not provide separate update channels.

The pinned [shared prerelease workflow](https://github.com/teh-hippo/common-repo-configs) verifies branch membership and stamps the packaged manifest.
Use the public tag for installation and metadata's source SHA and packaging version for runtime verification.
Source versions remain unchanged.
Publish a new candidate for later fixes.

## Recovering a failed publication

Recover publication using the existing version, exact commit and original notes.
Packages are verified before `gh release create` uploads through a draft and publishes.
An interrupted upload or cleanup can leave a draft.
Published releases and tags remain immutable.

For a PR candidate, retry the same exact SHA and version.
The publisher resolves existing tags, including annotated tags, to that exact commit.

For a failed master publication:

1. Stop other publication attempts for that tag and inspect the failed run.
   Confirm its versioning step completed and the remote tag exists.
   Check newer published versions; GitHub's latest stable must remain the newest stable release.
   Download its `release-<tag>` artefact, which preserves the release commit, tag, prerelease flag and original Semantic Release notes.
   Recovery requires that original metadata; investigate if it is missing.
2. Inspect `gh release view <tag> --json tagName,isDraft`.
   An already published release completes recovery.
   If an incomplete draft remains, confirm it is still a draft and remove only that draft with `gh release delete <tag> --yes`.
   Preserve the tag when deleting a draft.
3. Use a fresh worktree at the exact tag and download the metadata there.
   The following commands use an absolute path for the recovery worktree:

   ```bash
   tag=v7.40.1-rc.1
   run_id=123456789
   recovery=/absolute/path/to/release-recovery
   git fetch origin "refs/tags/$tag:refs/tags/$tag"
   git worktree add --detach "$recovery" "$tag"
   gh run download "$run_id" --name "release-$tag" --dir "$recovery/release-metadata"
   test "$(cat "$recovery/release-metadata/tag")" = "$tag"
   test "$(git -C "$recovery" rev-parse HEAD)" = "$(cat "$recovery/release-metadata/commit")"
   uv --directory "$recovery" sync --locked
   make -C "$recovery" clean package
   uv --directory "$recovery" run --no-sync python scripts/package.py \
     --source custom_components/ha_govee_led_ble --verify-archive dist/ha_govee_led_ble.zip
   ```

4. Verify the checksum, then invoke the same publisher with the saved identity and notes.
   The publisher rechecks the immutable remote tag.
   Run this only after the package verification above succeeds:

   ```bash
   (cd "$recovery/dist" && sha256sum --check ha_govee_led_ble.zip.sha256)
   GITHUB_REPOSITORY=teh-hippo/ha-govee-led-ble \
     bash "$recovery/scripts/publish-release.sh" \
       "$tag" "$(cat "$recovery/release-metadata/commit")" "$(cat "$recovery/release-metadata/prerelease")" \
       "$recovery/release-metadata/release-notes.md" \
       "$recovery/dist/ha_govee_led_ble.zip" "$recovery/dist/ha_govee_led_ble.zip.sha256" "$recovery/uv.lock"
   ```

Use the configured Node/Kaitai tools and authenticated GitHub CLI for recovery.
Recovery resumes asset publication with the saved versioning result.

## Qualifying on hardware

1. Capture the installed release and each test device's restorable state, including hidden mode and settings when a light is off.
2. Refresh the integration's repository in Marketplace, call `update.install` on its `update` entity with the exact RC tag as `version`, then restart Home Assistant.
3. Confirm the installed tag in Marketplace and the manifest version in diagnostics after the restart match the RC; download metadata alone does not prove restarted runtime code.
4. Exercise the affected workflows and require fresh BLE readback, not optimistic state.
5. Restore every device even when a test fails, and verify it by fresh readback.  Keep diagnostics private and report the exact RC, observed results and anything unverified.
