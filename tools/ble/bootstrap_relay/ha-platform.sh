#!/usr/bin/env bash
set -euo pipefail

action="${1:?status, disable or enable required}"
repo="${2:?repository path required}"
case "$action" in
  status|disable|enable) ;;
  *) echo "unsupported Home Assistant action" >&2; exit 2 ;;
esac

IFS= read -r entry_id
[ -n "$entry_id" ] || {
  echo "Home Assistant entry ID is absent from stdin" >&2
  exit 2
}

base="${HA_URL%/}"
case "$base" in
  https://*) HA_WEBSOCKET_URL="wss://${base#https://}/api/websocket" ;;
  http://*) HA_WEBSOCKET_URL="ws://${base#http://}/api/websocket" ;;
  *) echo "HA_URL must use HTTP or HTTPS" >&2; exit 2 ;;
esac
export HA_WEBSOCKET_URL

exec uv run --no-project --with websockets python3 \
  "$repo/tools/harness/ha_entry.py" \
  "$entry_id" \
  "$action"
