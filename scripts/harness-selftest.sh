#!/usr/bin/env bash
# No-hardware self-test of the BLE protocol validation harness.
#
# Builds every exact-compare frame from our own protocol.py and runs it back
# through the same decode + compare path a live capture uses. Guards
# encode<->decode symmetry and plan<->protocol drift; exits non-zero on any
# failure. It does NOT prove our bytes match a real Govee device -- only a
# live run (validate_protocol.py --live) can do that.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run python tools/ble/validate_protocol.py --sim "$@"
