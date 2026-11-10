# Release candidates

A release candidate (RC) is a prerelease package for live testing on hardware.
The [release policy](../CONTRIBUTING.md#releases) defines automatic master candidates, optional PR candidates and manually authorised stable releases.
RCs never move GitHub's latest stable release.
Use an RC, not SSH deployment or copying files.

## Selecting a candidate in Marketplace

Open **Settings > Marketplace**.
Candidates are available in the integration's download/redownload dialog's version selector.
Select the exact published tag; there is no need to enable prerelease updates just to install one candidate.
With prerelease updates disabled, normal update prompts remain stable-only.
Enabling prerelease updates instead opts into the shared feed of master and PR candidates.
Publishing a prerelease neither changes that user preference nor installs an update automatically.

## Master candidates

Merging release-bearing changes to `master` automatically publishes a candidate after current-master validation succeeds.
Python Semantic Release calculates the upcoming version and successive `v<version>-rc.<number>` tags, updating source versions and the lockfile through its normal release commit.
Maintenance-only changes do not force a new candidate.
Use the published master candidate containing the change; do not dispatch a second workflow just to recreate it.
Wait for the complete `Release` workflow and verify its ZIP and checksum before sharing the tag.
Stable publication is a separate operator decision, not a prerequisite for hardware testing.

## Building an optional PR candidate

Run the **Prerelease Package** workflow (`workflow_dispatch`) on the branch, after the final `make check` and with the reviewed commit pushed.
Obtain operator approval for a manual build/publication and its public notes.
Only `publish` is required.
The selected branch must have an open, same-repository PR targeting `master`.
Left blank, `target_sha` is the branch head, `version` is the next patch from the selected commit's manifest with `-pr-<PR number>.<candidate number>`, and `release_notes` is a generic candidate note.
For example, the first preview for PR #145 might be `v7.40.1-pr-145.1`, followed by `v7.40.1-pr-145.2`.
Candidate numbers advance from existing tags for that PR, without a separate stored counter.
Retrying the latest candidate's exact commit reuses its version; an explicit version must identify the selected PR.
This preview identifier is not a prediction of the eventual stable version.
An explicit `version` cannot be a stable version.
Set `publish=true` to create the `v<version>` tag and prerelease, which is what Marketplace installs.
Set `publish=false` for a build-only run: it uploads the package, checksum and metadata as a run artefact (`gh run download <run id>`) without releasing.
Publish another RC for later fixes rather than reusing a tag or hotpatching an installation.
The workflow delegates packaging to a pinned [shared prerelease workflow](https://github.com/teh-hippo/common-repo-configs), which checks that the exact SHA belongs to the branch and stamps only the build's manifest.
That shared interface accepts RC versions, so `7.40.1-pr-145.2` uses the internal packaging input `7.40.1-rc.2.pr-145`, producing manifest version `7.40.1rc2`.
The build metadata records that packaging input and the exact source SHA; the public tag identifies the PR and candidate.
It does not commit preview versions to the feature branch.
The master release checkout removes PR preview tags locally before running Semantic Release, preserving normal master numbering and release notes without changing remote tags.
For stable publication, that checkout also removes master-candidate tag refs locally so generated stable notes include the changes delivered through RCs.
Automatic master candidates retain their RC refs for native numbering.
The build checks package integrity; it does not replace the required prior review and `make check`.

## Recovering a failed publication

Version/tag creation and publication are separate operations.
The workflows verify packages before passing assets to `gh release create`, which uploads through a draft and publishes afterwards.
An upload failure is not an invitation to bump again, move a tag or overwrite a public release.
GitHub CLI normally cleans up its temporary draft on a handled failure; an interruption or failed cleanup can leave a draft.

For a PR candidate, retry the same exact SHA and version.
The publisher accepts an existing tag only after resolving it to that exact commit, including annotated tags.
It does not replace a published release.
Build-only runs do not reserve candidate numbers.

For a failed master publication:

1. Stop other publication attempts for that tag and inspect the failed run.
   Confirm its versioning step completed and the remote tag exists.
   Check for newer published versions before recovering an older tag; do not make a superseded stable release the latest.
   Download its `release-<tag>` artefact, which preserves the release commit, tag, prerelease flag and original Semantic Release notes.
   If that metadata is missing, stop and investigate rather than inventing another version or replacement notes.
2. Inspect `gh release view <tag> --json tagName,isDraft`.
   If already published, stop; do not overwrite its assets.
   If an incomplete draft remains, confirm it is still a draft and remove only that draft with `gh release delete <tag> --yes`.
   Never use `--cleanup-tag`.
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
   It checks the remote tag again and refuses to retarget it.
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
Do not rerun Semantic Release versioning or remove a published release to repair a failed upload.

## Qualifying on hardware

1. Capture the installed release and each test device's restorable state, including hidden mode and settings when a light is off.
2. Refresh the integration's repository in Marketplace, call `update.install` on its `update` entity with the exact RC tag as `version`, then restart Home Assistant.
3. Confirm the installed tag in Marketplace and the manifest version in diagnostics after the restart match the RC; download metadata alone does not prove restarted runtime code.
4. Exercise the affected workflows and require fresh BLE readback, not optimistic state.
5. Restore every device even when a test fails, and verify it by fresh readback.  Keep diagnostics private and report the exact RC, observed results and anything unverified.
