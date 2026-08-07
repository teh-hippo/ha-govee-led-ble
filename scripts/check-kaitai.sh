#!/usr/bin/env bash
# Kaitai gate: compile every schema before running the committed protocol fixtures.
#
# The generated *.py parsers are gitignored build products, so they go stale silently and
# a roundtrip run against a stale parser proves nothing. Always recompile before running.
set -euo pipefail
cd "$(dirname "$0")/.."

KAITAI=tools/ble/kaitai

if [ ! -d "$KAITAI/node_modules" ]; then
  echo "--- installing the Kaitai compiler toolchain"
  npm --prefix "$KAITAI" ci --silent
fi

echo "--- Compiling every spec"
for spec in "$KAITAI"/*.ksy; do
  node "$KAITAI/compile.js" "$spec" >/dev/null
  echo "  ok $(basename "$spec")"
done

echo "--- Running the .kst fixtures"
uv run --no-sync python "$KAITAI/kst_runner.py"
