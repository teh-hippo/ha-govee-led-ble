# Contributing

## Requesting support or suggesting fixes

Request a new model with a support-request issue and the exact SKU label (for example `H617A`); pull requests for a specific model carry the same label.
For a device-specific problem on a supported model, open an issue or pull request describing the behaviour you saw, with diagnostics.  Fixes are welcome as suggestions, and protocol corrections belong in the model's `.ksy` file.
Owner confirmations go on the model's confirmation child under [the owner-confirmation tracker](https://github.com/teh-hippo/ha-govee-led-ble/issues/442), not in new issues.
Do not post Bluetooth addresses, serial numbers, account details or other unique identifiers.

## Architecture

- `tools/ble/kaitai/**/*.ksy` is the only source of BLE wire structure and the protocol documentation.  Files under `speculative/` are unconfirmed hypotheses; the rest are evidence-backed.  `generated_protocol/` is build output and is never edited.
- `const.py` holds one `ModelProfile` per exact SKU, declaring its capabilities.  Compatible models may share a Kaitai adapter but never a whole profile.
- Keep offsets, command literals and packet enums out of entity and coordinator code.
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
Maintainers: see [docs/release-candidates.md](docs/release-candidates.md) for release-candidate qualification.
