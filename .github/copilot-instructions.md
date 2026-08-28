# Copilot instructions for `ha-govee-led-ble`

## Build, lint, and test commands

- Full local preflight (matches CI):  
  `make check`
- Completion gate: after making changes, `make check` must pass; if it fails, fix the issue and rerun until it passes, then capture any durable repo-specific lesson in these instructions.
- Canonical build:
  `make build`
- Reproducible package:
  `make package`
- Run a single test:  
  `uv run pytest tests/test_coordinator_status.py -q`

The Makefile owns build orchestration and the full local gate.

## High-level architecture

- This is a Home Assistant custom integration (`domain: ha_govee_led_ble`) for local BLE control of supported Govee models (currently H617A and H6199).
- `config_flow.py` handles discovery/manual setup, infers model from BLE local name, and creates config entries keyed by device address.
- `__init__.py` creates one `GoveeBLECoordinator` per config entry, performs first refresh, removes legacy entities, and forwards setup to the platforms listed in its `PLATFORMS` constant.
- The coordinator is split across `coordinator*.py`: BLE connect/reconnect lifecycle, notification subscription, keep-alive/state queries, optimistic state fields, and bounded raw packet logging for diagnostics.
- Kaitai schemas own wire structure. Modules in `generated_protocol/` are ignored build outputs generated deterministically from them; focused handwritten modules retain semantic transforms and transport framing.
- `light.py` is the primary control surface, with the custom services in `light_services.py`.
- Effect Studio profiles own interdependent H6199 Video settings rather than duplicating them as standalone entities.
- `scenes.py` loads the committed per-model scene snapshots used by light effect selection.

Name a module here only when something else in this file depends on knowing it exists. A full inventory rots: the last one still listed four platforms after there were seven.

## Key repository conventions

- Model capabilities are declared in `const.py` via `ModelProfile` fields such as `supports_scenes`, `supports_video_mode`, `supports_white_balance`, `supports_blank_screen`, `static_readback_echoes_color`, and segment fields. New model behaviour should be wired through a profile field first, then entity setup. `supports_segments` and `supports_music_mode` are derived properties, so check before trying to set them.
- Prefer root-cause refactoring over band-aid fixes; when behavior crosses layers, update shared paths instead of patching a single call site.
- Treat changes holistically across capabilities, protocol encode/decode, coordinator state handling, entity/service wiring, diagnostics, and tests so behavior stays consistent.
- Advanced Studio controls and saved-effect projection are capability-gated by the model profile and catalogue.
- Do not add wire offsets, literals or enums to entity/coordinator code. Put structure in Kaitai and keep only semantic transforms, checksums and transport framing handwritten.
- State writes are optimistic but guarded:
  - `light.py` uses `_rollback()` snapshots plus `_refresh_with_retry()` verification for state-readable models.
  - Effect Studio durable application uses the deployment engine's serialised prepare, write, verify and recovery path.
- Effect names are normalized (`_normalize_effect_name`) before lookup/comparison; preserve this normalization path when adding new effects/services.
- `make check` is the authoritative local validation flow and should stay aligned with `.github/workflows/validate.yml`.

## Protocol source of truth

- Captures are ground truth.
- `tools/ble/kaitai/*.ksy` is the only wire-structure source. Do not restate offsets,
  literals or enums elsewhere.
- Unknown attributes follow official Kaitai style and omit `id`. `reserved` means known
  unused. Unparsed transport chunks are not protocol unknowns.
- `govee_shared.ksy` contains structures independently exercised through both models;
  model-specific roots remain separate.
- `tests/test_kaitai_protocol.py` exercises representative byte constants directly through
  freshly generated parsers. Do not add a repository-specific fixture manifest or runner.
- `scripts/generate-kaitai.sh` calls Kaitai Struct Compiler 0.11 directly and can locate
  the pinned compiler through mise when it is not otherwise available. Java is an
  unpinned development/CI runtime only.
- Generated Python in `custom_components/ha_govee_led_ble/generated_protocol/` is
  ignored and never edited manually.
- After changing KSY, run `make protocol` and `make verify-protocol`.
- The public [`ios-ble-capture` methodology](https://github.com/teh-hippo/ios-ble-capture/blob/main/docs/methodology.md) describes capture, attribution and schema derivation.  This repository owns its KSY files and does not depend on that tool.
