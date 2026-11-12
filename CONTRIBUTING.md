# Contributing

## Requesting support or suggesting fixes

Request a new model with a support-request issue and the exact SKU label (for example `H617A`); pull requests for a specific model carry the same label.
For a device-specific problem on a supported model, open an issue or pull request describing the behaviour you saw, with diagnostics.  Fixes are welcome as suggestions, and protocol corrections belong in the model's `.ksy` file.
Owner confirmations go on the model's confirmation child under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442), not in new issues.
Do not post Bluetooth addresses, serial numbers, account details or other unique identifiers.

## Architecture

- Fix the cause rather than adding timing-based workarounds.  Prefer protocol acknowledgements, explicit state transitions and completion-driven backpressure; timeouts bound failures, not normal operation.
- A dropped BLE link still owns native client resources: call `disconnect()` even when `is_connected` is false.  Retired-client cleanup must be tracked, survive entry-background-task cancellation and be drained on entry teardown without altering a replacement client.
- Preserve native link failures and explicit session invalidation as `GoveeTransportError` through encryption wrappers.  Background polls handle it like `BleakError`; it must not enable foreground retries or hide programming errors, protocol rejection or ownership failures.
- `tools/ble/kaitai/**/*.ksy` is the only source of BLE wire structure and the protocol documentation.  Files under `speculative/` are unconfirmed hypotheses; the rest are evidence-backed.  `generated_protocol/` is build output and is never edited.
- Speculative schemas must retain unqualified suffix bytes; test nonzero tails rather than assuming zero padding when reusing shared types.
- `const.py` holds one `ModelProfile` per exact SKU, declaring its capabilities.  Compatible models may share a Kaitai adapter but never a whole profile.
  Products requiring subscription-qualified Pact must revoke confirmation on disconnect, retain cached identity only for presentation, and reconcile a fresh marker or current-subscription advertisement before writes.
  Reconcile expiring identity at operation boundaries before snapshotting generations; capability getters must be side-effect free.
- Aim for complete in-scope support on every evidenced revision, not discovery or capability flags alone.  Keep exact-model BLE documentation in Kaitai and product facts in profiles/catalogues; implement execution, editing and recovery through shared capability-driven paths, without per-model UI or manual packet workarounds.
- Apply observed physical geometry and its derived logical segment count together, using the declared product capacity rather than the current or original installed length.  Equivalent profile resolution must preserve observations and in-progress transactions.
- Bind prepared segment masks to their layout generation and BLE subscription.  Qualify wider masks per product without reinterpreting other models' opaque bytes.
- Keep offsets, command literals and packet enums out of entity and coordinator code.
- Every outbound frame goes through `_async_write_packet`, which waits for the previous `0x33` or `0xAA` frame's same-command reply before writing.  Never add per-feature sleeps to pace requests; `ReplyGate` learns commands that never reply on a subscription.
- Submit complete A3 uploads through `async_write_effect_sequence`.  Framing is validated before transmission, and each physical chunk stays bound to its ordered sequence and authorising header, including injected preview writers.
  Complete pending upload acknowledgements explicitly on subscription loss or profile invalidation; never poll for connection changes while awaiting an acknowledgement.
- Keep music upload boundaries and retained-body candidates in `MusicWriteSequence`, not packet state dictionaries.  Invalidate retained body knowledge at the first physical upload attempt, and install the candidate only after the complete sequence and required acknowledgement succeed.
- Arm reply tracking before the physical write, and accept only validated replies.  A late reply reinstates pacing for a command previously learned as silent; failed writes must not teach silence.
- Qualify observed colour mode against the latest mode-write generation, effective profile and current subscription.
  An expired optimistic expectation does not confirm a mode.
- Where selector readback is ambiguous, complete successful applications as `APPLIED` with `WRITE_COMPLETED` confidence, not confirmed or failed.
  Keep locally delivered editing context on the current subscription only; missing verification alone must not trigger rollback or retransmission.
- Plaintext marker compatibility is exact-model policy over a generated wire shape, never a generic malformed-marker fallback.
  Advertised or previously established encryption requirements always take precedence.
- Qualify revision-dependent effects before compilation and bind prepared packets to their encoding policy.
  Preview connection preparation must preserve foreground invalidation without allowing an older preview admission to invalidate a newer preparation.
- Qualify source power observations against the latest master-power write, effective profile and current subscription before using them to preserve siblings.
- Compile inline video settings from complete typed requests before the first mode write.
  Recover omitted mandatory values through qualified independent reads; retained cache values and successful writes are not fresh observations.
- Evaluate compound revision requirements together: a known failed prerequisite wins over missing identity, and missing identity never grants a control.
- Entity setters run through `GoveeBLEEntity._async_latest`: the first request sends at once, and while it runs only the newest queued request per control is sent.  Light on, off and attribute calls share one key, with queued `turn_on` attributes merged.  Services, Effect Studio and background work bypass it.
- Keep generic guarded commands independent of video qualification.  Track interrupted control attempts and uncertainty in coordinator-owned requests, not entity-local transactions.
- Declare source lights only for independently addressable power controls.
  Attach segment masks or master brightness only when they leave siblings unchanged; keep uncertain mappings neutral and state unconfirmed until observed.
  Declare source-specific colour modes and native attributes explicitly.
  Partitioned segment writes must cover each position exactly once and keep separately addressed sources out of segment masks.
  Run source turn-on as one coordinator-owned transaction, qualify preserved sibling state there, and reserve segment geometry only for segment-addressed writes.
- A new model needs its scene catalogue: run `uv run python tools/ble/refresh_scene_catalogues.py <SKU>` before registering its profile.  A workflow keeps existing catalogues current.
- Plans and findings for a model live in its issue or pull request, not in `docs/`.

## Support status

New models merge as `Experimental`.  An owner confirms working hardware in the model's confirmation issue, and a maintainer then sets `SupportQuality.SUPPORTED` in `const.py` and updates the README table.
An accepted write or another SKU's report is not confirmation.

## Repository non-goals

These apply to every model, including Experimental ones.  The repository does not expose:

- AI filters;
- Wi-Fi provisioning, cloud control, or account and network setup;
- on-device timers, countdowns or schedules (use Home Assistant automations);
- phone or host microphone capture, or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates;
- animated scene previews; or
- camera calibration that depends on Govee Wi-Fi or cloud services.

Decode-only Kaitai documentation of these is fine; runtime control is not.

## Development

Run `make protocol` after a fresh clone, a new worktree or any `.ksy` change, and `make check` before finishing.

## Releases

Keep `master` release-quality.
There are three publication paths:

- **Master candidates:** after a release-bearing change merges and `Validate` succeeds on current `master`, `Release` automatically publishes the upcoming version as `v<version>-rc.<number>`.
  Python Semantic Release calculates versions and release notes from Conventional Commits; `feat`, `fix`, `perf`, `build` and breaking changes drive releases.
  Documentation or maintenance alone does not force a candidate.
- **Optional PR candidates:** request a reviewed, exact-SHA build when hardware testing is needed before merge.
  `Prerelease Package` publishes `v<version>-pr-<PR number>.<candidate number>` tags, for example `v7.40.1-pr-145.1`.
  The master release checkout excludes these preview tags locally so they cannot affect master numbering or release notes; remote tags remain untouched.
  See [release candidates](docs/release-candidates.md) for publication and testing.
- **Stable releases:** the operator decides when current validated `master` is ready.
  Manually run `Release` on `master` (`gh workflow run release.yml --ref master`).
  Python Semantic Release creates the stable version, release commit, tag and notes; do not promote by editing a prerelease checkbox or choosing a version by hand.
  The stable checkout also excludes master-candidate tag refs locally, so its normal generated notes cover changes since the previous stable release.
  Automatic candidates retain those refs for native RC numbering; all remote tags remain untouched.

Each PR branch and each master publication type has its own concurrency group.
New requests replace older waiting requests only within the same group; active publication finishes.
Master RC and stable requests cannot cancel each other, but share a serial publication lock because both update master versions and tags.
Both require successful validation of the exact current master commit.
If master advances or its validation is incomplete, publication fails safely; wait for its checks and retry the manual action if needed.
Release commits do not recursively publish candidates.
Previous candidate tags and releases remain immutable history, with the newest master candidate available for testing.
Only stable publication moves GitHub's latest stable release.
No moving `latest` Git tag is required or maintained.

Marketplace users can select a candidate explicitly from the download/redownload dialog's version list without enabling prerelease updates.
Open Marketplace under **Settings > Marketplace** and use the integration's existing `update` entity for exact-version installation.
Keep prerelease updates disabled for stable-only update prompts; enabling them opts into both master and PR candidates.
Publishing a candidate does not opt users into that channel or install it automatically.

Every release carries the verified integration ZIP and SHA-256 checksum.
Semantic Release owns master versions, release commits, tags and notes but defers GitHub release creation.
After packaging and verification, GitHub CLI stages a draft while uploading assets and publishes only once those uploads succeed.
Failed publication may leave a tag or draft, not a deliberately published assetless release.
Retry only against the same exact commit; never move an existing tag or overwrite a published release.
See [release recovery](docs/release-candidates.md#recovering-a-failed-publication) for exact-tag recovery without creating another version.
Merging a model does not imply hardware confirmation or promote it from Experimental.
