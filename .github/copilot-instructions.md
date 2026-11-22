# Copilot instructions for `ha-govee-led-ble`

## Canonical contributor guidance

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) before planning or implementing changes.
It owns architecture, test design, acceptance and release policy.
Record contributor-wide lessons there and agent-only lessons here.

## Build, lint, and test commands

The Makefile owns orchestration.
Use `make check-fast` while iterating and finish with a passing `make check`.
Use `make build` for generated outputs and `make package` for a requested distributable.
For a focused test: `uv run pytest tests/test_coordinator_status.py -q`.

## Agent-specific reminders

- Use the four-section plan in `.github/PULL_REQUEST_TEMPLATE.md` for new-model work.
- Keep local rebase recovery refs outside `refs/heads/` and use `--no-update-refs` from the first invocation.
  Preserve Git's generated `update-ref` commands in an active rebase.
- Follow `docs/release-candidates.md` for hardware qualification.
