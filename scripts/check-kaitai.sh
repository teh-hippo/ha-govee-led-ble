#!/usr/bin/env bash
# Kaitai gate: test every schema, then require committed runtime modules to be current.
set -euo pipefail
cd "$(dirname "$0")/.."

KAITAI=tools/ble/kaitai
RUNTIME=custom_components/ha_govee_led_ble/generated_protocol
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "--- Compiling every spec"
bash scripts/generate-kaitai.sh all "$work/all" >/dev/null

echo "--- Running the .kst fixtures"
KAITAI_GENERATED_DIR="$work/all" uv run --no-sync python "$KAITAI/kst_runner.py"

echo "--- Checking committed runtime modules"
bash scripts/generate-kaitai.sh runtime "$work/runtime" >/dev/null
if ! diff -ru --exclude='__pycache__' --exclude='*.pyc' "$RUNTIME" "$work/runtime"; then
  echo "Generated protocol modules are stale; run: bash scripts/generate-kaitai.sh runtime" >&2
  exit 1
fi
