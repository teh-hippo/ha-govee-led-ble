# Copilot instructions for `ha-govee-led-ble`

## Canonical contributor guidance

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) before planning or implementing changes.
It owns architecture, test design, acceptance and release policy.
Record contributor-wide lessons there and agent-only lessons here.

## Build, lint, and test commands

The Makefile owns orchestration.
Run `make bootstrap` for a new checkout.
Use the narrowest relevant command while iterating: a focused pytest file, frontend `typecheck`/`test:unit`, or the affected generated-output target.
Use `make check-fast` for a broad checkpoint and finish with a passing `make check`.
Use `make package` only for a requested distributable.

Read the relevant local guidance before editing:

- `.github/instructions/backend.instructions.md` for Python backend and tests;
- `.github/instructions/frontend.instructions.md` for frontend code and fixtures;
- `.github/instructions/protocol.instructions.md` for Kaitai/protocol work.

## Agent-specific reminders

- Use the four-section plan in `.github/PULL_REQUEST_TEMPLATE.md` for new-model work.
- Keep local rebase recovery refs outside `refs/heads/` and use `--no-update-refs` from the first invocation.
  Preserve Git's generated `update-ref` commands in an active rebase.
- Follow `docs/release-candidates.md` for hardware qualification.
- Run independent pytest processes serially within one checkout and use the suite's configured workers.
