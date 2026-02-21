#!/usr/bin/env bash
# Local preflight — mirrors CI exactly. Run before every push.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Lint ==="
uv run ruff check .
uv run ruff format --check .

echo "=== Mypy ==="
uv run mypy custom_components/ha_govee_led_ble tests

echo "=== Test + Coverage ==="
uv run coverage run -m pytest tests/ -v --tb=short
uv run coverage report --include="custom_components/ha_govee_led_ble/*" --fail-under=90

echo ""
echo "✅ All checks passed — safe to push."
