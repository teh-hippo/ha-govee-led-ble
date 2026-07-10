#!/usr/bin/env bash
# Local preflight for the Lovelace card — mirrors the frontend CI workflow.
# Run before every push that touches frontend/ or the committed card bundle.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DIST="frontend/dist/govee-led-ble-card.js"
BUNDLE="custom_components/ha_govee_led_ble/www/govee-led-ble-card.js"

cd frontend

echo "=== Install (frozen lockfile) ==="
bun install --frozen-lockfile

echo "=== Typecheck ==="
bun run typecheck

echo "=== Test ==="
bun run test

echo "=== Build ==="
bun run build

cd "$REPO_ROOT"

echo "=== Build freshness ==="
# The build is byte-reproducible with the pinned bun version, so the committed
# bundle must match what we just rebuilt into frontend/dist/.
if ! cmp -s "$DIST" "$BUNDLE"; then
  echo "❌ Committed card bundle is stale."
  echo "   Fresh build: $DIST"
  echo "   Committed:   $BUNDLE"
  echo "   Copy the rebuilt bundle in and commit it:"
  echo "     cp $DIST $BUNDLE"
  exit 1
fi
echo "Committed bundle matches the fresh build."

echo ""
echo "✅ All frontend checks passed — safe to push."
