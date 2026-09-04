# Copilot instructions for `ha-govee-led-ble`

## Build, lint, and test commands

- Full local preflight (matches CI):  
  `make check`
- Completion gate: after making changes, `make check` must pass; if it fails, fix the issue and rerun until it passes.
  Record contributor-wide lessons in `CONTRIBUTING.md` and agent-only lessons here.
- Canonical build:
  `make build`
- Reproducible package:
  `make package`
- Run a single test:  
  `uv run pytest tests/test_coordinator_status.py -q`

The Makefile owns build orchestration and the full local gate.

## Canonical contributor guidance

Read and follow [`CONTRIBUTING.md`](../CONTRIBUTING.md) before planning or implementing changes.  It is the provider-agnostic source for:

- project structure and model architecture;
- new-model research and planning;
- support quality and promotion;
- Kaitai protocol ownership and speculative schemas;
- exact-SKU scene catalogues;
- repository non-goals; and
- validation.

Do not duplicate those rules here.  Update `CONTRIBUTING.md` when a contributor-wide invariant changes.

## Agent-specific reminders

- Use the four-section new-model plan from `CONTRIBUTING.md`; do not invent a provider-specific planning format.
- Trace the complete affected path before editing, then prefer shared profile, adapter, coordinator, and test paths over model-specific duplicates.
- Never edit generated protocol or frontend outputs manually.
- Run focused existing checks while iterating and `make check` before declaring the final tree complete.
- Run `make package` only when a distributable archive is requested.
