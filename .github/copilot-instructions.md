# Copilot instructions for `ha-govee-led-ble`

## Build, lint, and test commands

- Full local preflight (matches CI):  
  `bash scripts/check.sh`
- Completion gate: after making changes, `bash scripts/check.sh` must pass; if it fails, fix the issue and rerun until it passes, then capture any durable repo-specific lesson in these instructions.
- Run a single test:  
  `uv run pytest tests/test_protocol.py::test_parse -q`

`check.sh` owns the stage list and the exact flags. Do not restate them here: a second copy drifts silently, and the version that lived here had already lost the `--no-sync` the script uses.

## High-level architecture

- This is a Home Assistant custom integration (`domain: ha_govee_led_ble`) for local BLE control of supported Govee models (currently H617A and H6199).
- `config_flow.py` handles discovery/manual setup, infers model from BLE local name, and creates config entries keyed by device address.
- `__init__.py` creates one `GoveeBLECoordinator` per config entry, performs first refresh, removes legacy entities, and forwards setup to the platforms listed in its `PLATFORMS` constant.
- The coordinator is split across `coordinator*.py`: BLE connect/reconnect lifecycle, notification subscription, keep-alive/state queries, optimistic state fields, and bounded raw packet logging for diagnostics.
- Kaitai schemas own wire structure. Committed modules in `generated_protocol/` are generated from them; handwritten protocol code is only a temporary migration layer.
- `light.py` is the primary control surface, with the custom services in `light_services.py`.
- `h6199_controls.py` contains shared advanced control entities for Number/Select/Switch; `number.py`, `select.py`, and `switch.py` are thin entry-point wrappers.
- `scenes.py` stores and decodes the H617A scene catalog used by light effect selection.

Name a module here only when something else in this file depends on knowing it exists. A full inventory rots: the last one still listed four platforms after there were seven.

## Key repository conventions

- Model capabilities are declared in `const.py` via `ModelProfile` fields (`supports_video_mode`, `supports_diy`, `static_readback_echoes_color`, etc.); new model behavior should be wired through a profile field first, then entity setup. Some capabilities are derived rather than declared (`supports_segments`, `supports_music_mode`, `custom_effect_kinds` are properties), so check before trying to set one.
- Prefer root-cause refactoring over band-aid fixes; when behavior crosses layers, update shared paths instead of patching a single call site.
- Treat changes holistically across capabilities, protocol encode/decode, coordinator state handling, entity/service wiring, diagnostics, and tests so behavior stays consistent.
- Advanced entities are capability-gated at setup time (see `h6199_controls.py`), so unsupported controls are not created for a model.
- Do not add wire offsets, literals or enums to entity/coordinator code. Put structure in Kaitai and keep only semantic transforms, checksums and transport framing handwritten.
- State writes are optimistic but guarded:
  - `light.py` uses `_rollback()` snapshots plus `_refresh_with_retry()` verification for state-readable models.
  - `h6199_controls.py` uses `_set_with_rollback()` around reapply callbacks.
- Effect names are normalized (`_normalize_effect_name`) before lookup/comparison; preserve this normalization path when adding new effects/services.
- `scripts/check.sh` is treated as the authoritative local validation flow and should stay aligned with `.github/workflows/validate.yml`.

## Protocol source of truth

- Captures are ground truth.
- `tools/ble/kaitai/*.ksy` is the only wire-structure source. Do not restate offsets,
  literals or enums elsewhere.
- Unknown attributes follow official Kaitai style and omit `id`. `reserved` means known
  unused. Unparsed transport chunks are not protocol unknowns.
- `govee_shared.ksy` contains structures independently exercised through both models;
  model-specific roots remain separate.
- Every fixture has machine-readable provenance and a committed SHA-256. Cross-fixture
  claims live in `spec/_aggregates.yaml`; the runner hard-fails missing, skipped or stale
  coverage.
- `scripts/generate-kaitai.sh` uses the pinned Kaitai compiler from `mise.toml`. Java is
  an unpinned development/CI runtime only.
- Generated Python in `custom_components/ha_govee_led_ble/generated_protocol/` is
  committed and never edited manually.
- After changing KSY or fixtures, run `bash scripts/check-kaitai.sh`.

## Captures: one capture, one light

A phone stays paired with every Govee device in the house, so an HCI capture is not evidence about a model until it is attributed. Two mechanisms enforce that, and both exist because the failure they catch reads as absence rather than as an error.

- `decode_govee.py` refuses to print a capture holding more than one Govee SOURCE, where a source is one BLE CONNECTION rather than one address. Narrow it with `--source <address, address tail or connection>`; `--all-peers` dumps it mixed on purpose. The address is used whenever the capture saw the connection open, so a light that reconnects mid-capture stays one source; otherwise the ATT connection handle is, printed as `?conn-0x4e`, because the address is the field that goes missing and a count keyed on it reports one source for a capture holding several. Keying on the address alone let a two-connection session through on 2026-08-05: all 2191 Govee-shaped frames were unaddressed, so they counted as one bucket and printed clean. Start the capture FIRST, then force a fresh connect, so the HCI connect event carrying the address lands inside the window.
- `--allow-unattributed` accepts ONE thing: that some frames belong to a connection the capture never saw open, so no address is known for them. It does NOT suppress the multi-source refusal. Those are separate claims, and `govee-capture.sh` passes it on every unbound `stop`, so a flag that covered both would disarm the guard at the call site that swallowed the failing session.
- `up.sh app` binds the session to the address it is supposed to be of, and `govee-capture.sh stop` fails when the capture holds none of that peer's frames. A session where the vendor app never reached the light otherwise decodes clean and empty, which reads as a quiet device. An unbound `stop` checks the weaker thing it still can: that the capture holds one connection's worth of Govee traffic.
- `analyse_capture.py` carries the same guard and offers no way to mix on purpose, because it CONCATENATES frames into a body: two sources there do not produce a mixed listing, they produce a body no device ever sent.
- Twenty bytes with a valid XOR is a 1-in-256 accident, so `_is_govee` admits foreign traffic and the second source in a capture is not necessarily another Govee device. The connection is what tells them apart; the shape never could.

Identity lives only in the untracked `devices.local.env`. A device the harness may drive directly has a `DEVICE_BLE_ADDRESS`; an app-sniff-only device must NOT, because `up.sh direct` refuses on the absence of that value. Its address goes in `DEVICE_SNIFF_ADDRESS` instead, which is used for attribution alone: `devices.env` asserts no value there can reach `DEVICE_ADDRESS`, so listing a device there does not make it drivable. Fake addresses in tracked files keep the real Govee OUI (`D0:35:34` for the H617A family, `D5:36:36` for the H6199 family) and an obviously invented tail, so they stay recognisable without being anyone's device.
