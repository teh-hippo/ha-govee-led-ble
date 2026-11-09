# Contributing

## Requesting support or suggesting fixes

Request a new model with a support-request issue and the exact SKU label (for example `H617A`); pull requests for a specific model carry the same label.
For a device-specific problem on a supported model, open an issue or pull request describing the behaviour you saw, with diagnostics.  Fixes are welcome as suggestions, and protocol corrections belong in the model's `.ksy` file.
Owner confirmations go on the model's confirmation child under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442), not in new issues.
Do not post Bluetooth addresses, serial numbers, account details or other unique identifiers.

## Architecture

- Fix the cause rather than adding timing-based workarounds.  Prefer protocol acknowledgements, explicit state transitions and completion-driven backpressure; timeouts bound failures, not normal operation.
- A dropped BLE link still owns native client resources: call `disconnect()` even when `is_connected` is false.  Retired-client cleanup must be tracked, survive entry-background-task cancellation and be drained on entry teardown without altering a replacement client.
- `tools/ble/kaitai/**/*.ksy` is the only source of BLE wire structure and the protocol documentation.  Files under `speculative/` are unconfirmed hypotheses; the rest are evidence-backed.  `generated_protocol/` is build output and is never edited.
- Speculative schemas must retain unqualified suffix bytes; test nonzero tails rather than assuming zero padding when reusing shared types.
- `const.py` holds one `ModelProfile` per exact SKU, declaring its capabilities.  Compatible models may share a Kaitai adapter but never a whole profile.
  Products requiring subscription-qualified Pact must revoke confirmation on disconnect, retain cached identity only for presentation, and reconcile a fresh marker or current-subscription advertisement before writes.
- Aim for complete in-scope support on every evidenced revision, not discovery or capability flags alone.  Keep exact-model BLE documentation in Kaitai and product facts in profiles/catalogues; implement execution, editing and recovery through shared capability-driven paths, without per-model UI or manual packet workarounds.
- Apply observed physical geometry and its derived logical segment count together, using the declared product capacity rather than the current or original installed length.  Equivalent profile resolution must preserve observations and in-progress transactions.
- Bind prepared segment masks to their layout generation and BLE subscription.  Qualify wider masks per product without reinterpreting other models' opaque bytes.
- Keep offsets, command literals and packet enums out of entity and coordinator code.
- Every outbound frame goes through `_async_write_packet`, which waits for the previous `0x33` or `0xAA` frame's same-command reply before writing.  Never add per-feature sleeps to pace requests; `ReplyGate` learns commands that never reply on a subscription.
- Arm reply tracking before the physical write, and accept only validated replies.  A late reply reinstates pacing for a command previously learned as silent; failed writes must not teach silence.
- Qualify observed colour mode against the latest mode-write generation, effective profile and current subscription.
  An expired optimistic expectation does not confirm a mode.
- Qualify revision-dependent effects before compilation and bind prepared packets to their encoding policy.
  Preview connection preparation must preserve foreground invalidation without allowing an older preview admission to invalidate a newer preparation.
- Qualify source power observations against the latest master-power write, effective profile and current subscription before using them to preserve siblings.
- Compile inline video settings from complete typed requests before the first mode write.
  Recover omitted mandatory values through qualified independent reads; retained cache values and successful writes are not fresh observations.
- Evaluate compound revision requirements together: a known failed prerequisite wins over missing identity, and missing identity never grants a control.
- Entity setters run through `GoveeBLEEntity._async_latest`: the first request sends at once, and while it runs only the newest queued request per control is sent.  Light on, off and attribute calls share one key, with queued `turn_on` attributes merged.  Services, Effect Studio and background work bypass it.
- Declare source lights only for independently addressable power controls.
  Attach segment masks or master brightness only when they leave siblings unchanged; keep uncertain mappings neutral and state unconfirmed until observed.
  Declare source-specific colour modes and native attributes explicitly.
  Partitioned segment writes must cover each position exactly once and keep separately addressed sources out of segment masks.
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
Publish releases only after the verified installation ZIP and checksum have been uploaded, so incomplete releases are never offered for installation.
Release candidates for hardware testing can be built from any branch: see [docs/release-candidates.md](docs/release-candidates.md).
