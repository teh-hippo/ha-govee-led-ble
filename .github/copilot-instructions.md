# Copilot instructions for `ha-govee-led-ble`

## Build, lint, and test commands

- Full local preflight (matches CI):  
  `bash scripts/check.sh`
- Completion gate: after making changes, `bash scripts/check.sh` must pass; if it fails, fix the issue and rerun until it passes, then capture any durable repo-specific lesson in these instructions.
- Lint only:  
  `uv run ruff check .`  
  `uv run ruff format --check .`
- Type-check only:  
  `uv run mypy custom_components/ha_govee_led_ble tests`
- Full test suite with coverage gate used in CI:  
  `uv run coverage run -m pytest tests/ -v --tb=short`  
  `uv run coverage report --include="custom_components/ha_govee_led_ble/*" --fail-under=90`
- Run a single test:  
  `uv run pytest tests/test_protocol.py::test_parse -q`

## High-level architecture

- This is a Home Assistant custom integration (`domain: ha_govee_led_ble`) for local BLE control of supported Govee models (currently H617A and H6199).
- `config_flow.py` handles discovery/manual setup, infers model from BLE local name, and creates config entries keyed by device address.
- `__init__.py` creates one `GoveeBLECoordinator` per config entry, performs first refresh, removes legacy entities, and forwards setup to `light`, `number`, `select`, and `switch` platforms.
- `coordinator.py` is the runtime core: BLE connect/reconnect lifecycle, notification subscription, keep-alive/state queries, optimistic state fields, and bounded raw packet logging for diagnostics.
- `protocol.py` is the single source of truth for BLE packet encoding/decoding (20-byte packets with XOR checksum), including query packets and parsing of color-mode status payloads.
- `light.py` is the primary control surface: core light behavior, effects/scenes handling, and custom services (`set_video_mode`, `set_music_mode`, `set_white_brightness`).
- `h6199_controls.py` contains shared advanced control entities for Number/Select/Switch; `number.py`, `select.py`, and `switch.py` are thin entry-point wrappers.
- `scenes.py` stores and decodes the H617A scene catalog used by light effect selection.

## Key repository conventions

- Model capabilities are declared in `const.py` via `ModelProfile` flags (`supports_video_mode`, `supports_music_mode`, etc.); new model behavior should be wired through profile flags first, then entity setup.
- Prefer root-cause refactoring over band-aid fixes; when behavior crosses layers, update shared paths instead of patching a single call site.
- Treat changes holistically across capabilities, protocol encode/decode, coordinator state handling, entity/service wiring, diagnostics, and tests so behavior stays consistent.
- Advanced entities are capability-gated at setup time (see `h6199_controls.py`), so unsupported controls are not created for a model.
- Keep BLE packet construction/parsing centralized in `protocol.py`; do not hardcode packet bytes in entity/coordinator code.
- State writes are optimistic but guarded:
  - `light.py` uses `_rollback()` snapshots plus `_refresh_with_retry()` verification for state-readable models.
  - `h6199_controls.py` uses `_set_with_rollback()` around reapply callbacks.
- Effect names are normalized (`_normalize_effect_name`) before lookup/comparison; preserve this normalization path when adding new effects/services.
- `scripts/check.sh` is treated as the authoritative local validation flow and should stay aligned with `.github/workflows/validate.yml`.
