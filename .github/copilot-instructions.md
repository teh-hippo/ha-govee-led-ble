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

Read and follow [`CONTRIBUTING.md`](../CONTRIBUTING.md) before planning or implementing changes; do not duplicate its rules here.  Update it when a contributor-wide invariant changes.

## Agent-specific reminders

- Use the four-section plan in `.github/PULL_REQUEST_TEMPLATE.md` for new-model work; do not invent a provider-specific planning format.
- Apply the architecture and change/test-design rules in `CONTRIBUTING.md` before proposing an implementation.
  Group work by root cause and shared contract, not by device or count of findings.
- Before adding special treatment, classify the difference and explain why an existing declaration, codec or shared operation cannot express it.
  Challenge the proposed abstraction too; neither a local exception nor a new framework is the default.
- Review the complete resulting path, including affected callers and removed code, rather than checking only the reporting device or added lines.
  Record reusable contributor invariants in `CONTRIBUTING.md`, not named-function recipes or a growing list of past incidents here.
- Never edit generated protocol or frontend outputs manually.
- Run focused existing checks while iterating and `make check` before declaring the final tree complete.
- Run `make package` only when a distributable archive is requested.
- For local rebases, keep recovery refs outside `refs/heads/` and use `--no-update-refs` from the first invocation.  Do not remove `update-ref` commands by hand from an active rebase.
- Follow `CONTRIBUTING.md` for release policy and `docs/release-candidates.md` for hardware testing.
  Master candidates publish automatically after validated release-bearing merges; stable publication is the operator's manual decision.
  Optional PR candidate builds/publication and public notes need approval.
