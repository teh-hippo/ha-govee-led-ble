#!/usr/bin/env bash
# Run the same checks as CI — use before every push.
# Usage: ./scripts/preflight.sh
set -euo pipefail

echo "=== Lint ==="
uv run ruff check custom_components/ tests/

echo "=== Format ==="
uv run ruff format --check custom_components/ tests/

echo "=== Test + Coverage ==="
uv run coverage run -m pytest tests/ -v --tb=short
uv run coverage report --include="custom_components/govee_ble_lights/*" --fail-under=90

echo ""
echo "✅ All checks passed — safe to push."
