#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO_DIR:-$HOME/ha-govee-led-ble}"
python="$repo/.venv/bin/python"
action="${1:-}"
network=""

if [ "$action" = provision ] || [ "$action" = validate-input ]; then
  network="$(cat)"
fi

export HARNESS_PHONE_BACKEND=windows
export HARNESS_BLE_BACKEND=windows
source "$repo/tools/harness/phone.sh"
resolve_device dreamtv

redact_output() {
  sed -E \
    -e '/^[[:space:]]+WRITE[[:space:]]/d' \
    -e 's/([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}/<redacted>/g'
}

query_versions() {
  require_bluetooth_transport
  govee_send send \
    aa060000000000000000000000000000000000ac \
    aa070300000000000000000000000000000000ae \
    aa2000000000000000000000000000000000008a \
    aa2100000000000000000000000000000000008b \
    --checksum raw \
    --response no \
    --model H6199 \
    --listen 6 \
    --gap 0.3 \
    --timeout 15 \
    --address "$DEVICE_EXPECTED_PEER" 2>&1 |
    redact_output |
    sed -E 's/^  NOTIFY/  REPLY/'
}

provision() {
  local link_output provision_output provision_status
  require_bluetooth_transport
  trap 'unset network' EXIT

  printf '%s\n' "$network" |
    "$python" "$repo/tools/ble/wifi_provision.py" compare

  link_output="$(govee_send send \
    aa060000000000000000000000000000000000ac \
    --checksum raw \
    --response no \
    --model H6199 \
    --listen 4 \
    --timeout 15 \
    --address "$DEVICE_EXPECTED_PEER" 2>&1 |
    redact_output)"
  printf '%s\n' "$link_output"
  grep -q 'NOTIFY' <<<"$link_output"

  if [ -n "${BLE_WRITE_INTENT_PATH:-}" ]; then
    case "$BLE_WRITE_INTENT_PATH" in
      /*) ;;
      *) echo "BLE write intent path must be absolute" >&2; return 2 ;;
    esac
    umask 077
    : >"$BLE_WRITE_INTENT_PATH"
  fi

  set +e
  provision_output="$(
    printf '%s\n' "$network" |
      "$python" "$repo/tools/ble/wifi_provision.py" build |
      govee_send send - \
        --response no \
        --model H6199 \
        --address "$DEVICE_EXPECTED_PEER" \
        --gap 0.3 \
        --listen 40 2>&1 |
      redact_output
  )"
  provision_status=$?
  set -e
  printf '%s\n' "$provision_output"
  if [ "$provision_status" -ne 0 ] && ! grep -q 'NOTIFY.*a11100' <<<"$provision_output"; then
    return "$provision_status"
  fi
  grep -q 'NOTIFY.*a11100' <<<"$provision_output"
}

validate_input() {
  printf '%s\n' "$network" |
    "$python" "$repo/tools/ble/wifi_provision.py" compare
}

case "$action" in
  preflight)
    require_bluetooth_transport
    echo "Windows BLE transport: ready"
    ;;
  query-versions) query_versions ;;
  validate-input) validate_input ;;
  provision) provision ;;
  *)
    echo "usage: $0 preflight|query-versions|validate-input|provision" >&2
    exit 2
    ;;
esac
