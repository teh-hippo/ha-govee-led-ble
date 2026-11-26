# Copilot instructions for `ha-govee-led-ble`

## Canonical contributor guidance

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) before planning or implementing changes.
It owns architecture, test design, acceptance and release policy.
Record contributor-wide lessons there and agent-only lessons here.

## Build, lint, and test commands

Use the [Makefile targets in CONTRIBUTING](../CONTRIBUTING.md#development) for setup and validation.
Source-only investigations do not require generated outputs; state any checks that need unavailable prerequisites.

Read the relevant local guidance before editing:

- `.github/instructions/backend.instructions.md` for Python backend and tests;
- `.github/instructions/frontend.instructions.md` for frontend code and fixtures;
- `.github/instructions/protocol.instructions.md` for Kaitai/protocol work.

## Agent-specific reminders

- Use the [PR template](PULL_REQUEST_TEMPLATE.md) for new-model work.
- Keep local rebase recovery refs outside `refs/heads/` and use `--no-update-refs` from the first invocation.
  Preserve Git's generated `update-ref` commands in an active rebase.
- Follow the [release candidate guide](../docs/release-candidates.md) for hardware qualification.
