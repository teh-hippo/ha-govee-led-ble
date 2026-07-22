#!/usr/bin/env bash
# Local preflight — mirrors CI exactly. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync --locked

echo "=== Lint ==="
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync python tools/ble/kaitai/evidence_lint.py

echo "=== Mypy ==="
uv run --no-sync mypy custom_components/ha_govee_led_ble tests

echo "=== Test + Coverage ==="
uv run --no-sync coverage run -m pytest tests/ -v --tb=short
uv run --no-sync coverage report --include="custom_components/ha_govee_led_ble/*" --fail-under=90

echo ""
echo "✅ All checks passed — safe to push."
