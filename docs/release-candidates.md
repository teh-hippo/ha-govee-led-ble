# Release candidates

A release candidate (RC) is a prerelease package built from any branch for live testing on hardware.  RCs never move GitHub's latest release, and feature branches keep the stable source version.
Agents and contributors can request one whenever testing on a device needs it; use an RC, not SSH deployment or copying files.

## Building one

Run the **Prerelease Package** workflow (`workflow_dispatch`) on the branch, after the final `make check` and with the reviewed commit pushed.
Only `publish` is required.  Left blank, `target_sha` is the branch head, `version` is the next patch with `-rc.<run number>.<branch>`, and `release_notes` is a generic candidate note.
Set `publish=true` to create the tag and prerelease; `publish=false` uploads the package, checksum and metadata without releasing.
Publish another RC for later fixes rather than reusing a tag or hotpatching an installation.
The workflow delegates to a pinned [shared prerelease workflow](https://github.com/teh-hippo/common-repo-configs), which stamps only the artifact manifest (`7.13.1-rc.2.h6102` becomes `7.13.1rc2`).

## Qualifying on hardware

1. Capture the installed release and each test device's restorable state, including hidden mode and settings when a light is off.
2. Refresh the integration's HACS `update` entity with `homeassistant.update_entity`, call `update.install` with the exact RC tag as `version`, then restart Home Assistant.
3. Confirm the running manifest version in diagnostics matches the RC; HACS metadata alone proves only downloaded files.
4. Exercise the affected workflows and require fresh BLE readback, not optimistic state.
5. Restore every device even when a test fails, and verify it by fresh readback.  Keep diagnostics private and report the exact RC, observed results and anything unverified.
