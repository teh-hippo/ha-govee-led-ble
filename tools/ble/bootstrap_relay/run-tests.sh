#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO_DIR:-$HOME/ha-govee-led-ble}"

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONDONTWRITEBYTECODE=1

exec uv run --project "$repo" --no-sync pytest \
  --rootdir "$here" \
  -c "$here/pyproject.toml" \
  "$here/tests" \
  "$@"
