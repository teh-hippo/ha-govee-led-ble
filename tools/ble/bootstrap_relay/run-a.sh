#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO_DIR:-$HOME/ha-govee-led-ble}"
platform_helper="${BWS_PLATFORM_HELPER:-$HOME/.copilot/skills/platform/scripts/platform-bws.sh}"
python="$repo/.venv/bin/python"
identity="$repo/tools/harness/devices.local.env"
live_dir="$root/live"
baseline_marker="$live_dir/baseline-passed.json"
identity_loaded=0
dreamtv_entry=""
active_run_id=""
active_unifi_state=""
network_attempted=0
device_touched=0
relay_intended=0
swap_intended=0
ha_release_intended=0
restored=0
ble_write_intent=""

umask 077
mkdir -p "$live_dir"
chmod 700 "$live_dir"

unifi() {
  bash "$platform_helper" run UNIFI -- bash -lc "$1"
}

proxmox() {
  bash "$platform_helper" run PROXMOX -- bash "$root/ai-lab.sh" "$@"
}

windows_ble() {
  bash "$root/windows-ble.sh" "$@"
}

load_identity() {
  [ "$identity_loaded" = 1 ] && return
  [ -r "$identity" ] || {
    echo "device identity file is absent" >&2
    return 1
  }
  source "$identity"
  dreamtv_entry="${DEVICE_HA_ENTRY[dreamtv]}"
  identity_loaded=1
}

ha_raw() {
  local action=$1
  load_identity
  printf '%s\n' "$dreamtv_entry" |
    bash "$platform_helper" run HA -- bash "$root/ha-platform.sh" "$action" "$repo"
}

ha_status() {
  ha_raw status | "$python" -c '
import json
import sys

value = json.load(sys.stdin)
print(json.dumps({
    "state": value.get("state"),
    "disabled_by": value.get("disabled_by"),
    "reason": value.get("reason"),
}, sort_keys=True))
'
}

ha_disable() {
  ha_raw disable | grep -qi '"success": true'
}

ha_enable() {
  ha_raw enable | grep -qi '"success": true'
}

ha_wait_loaded() {
  local value=""
  for _ in $(seq 1 6); do
    value="$(ha_status)"
    if grep -q '"state": "loaded"' <<<"$value" &&
       grep -q '"disabled_by": null' <<<"$value"; then
      printf '%s\n' "$value"
      return 0
    fi
    sleep 10
  done
  printf '%s\n' "$value" >&2
  return 1
}

unifi_command() {
  local command=$1
  shift
  local quoted=()
  local argument
  for argument in "$@"; do
    printf -v argument '%q' "$argument"
    quoted+=("$argument")
  done
  unifi "cd $(printf '%q' "$root") &&
    export PYTHONPATH=. &&
    $(printf '%q' "$python") -m govee_relay.unifi $command ${quoted[*]}"
}

preflight() {
  local run_id="${1:-run-a-ready}"
  local plan_file="$live_dir/unifi-plan.json"
  test ! -e "$live_dir/unifi-$run_id.json"
  PYTHONPATH="$root" "$python" -m govee_relay.unifi plan \
    --run-id "$run_id" \
    --relay-ip 192.168.0.167 \
    --vlan 30 >"$plan_file"
  chmod 600 "$plan_file"
  unifi_command check \
    --run-id "$run_id" \
    --relay-ip 192.168.0.167 \
    --vlan 30
  proxmox deploy
  proxmox test
  proxmox preflight
  windows_ble preflight
  ha_wait_loaded
  git -C "$repo" status --porcelain | grep -q . && {
    echo "public repository is not clean" >&2
    return 1
  }
  echo "READY: offline rehearsal, live-host TLS prewarm, UniFi conflict check, BLE transport preflight and HA ownership check passed."
}

generate_credentials() {
  "$python" - <<'PY'
import secrets
import string

alphabet = string.ascii_uppercase + string.digits
password = string.ascii_letters + string.digits
values = [
    "".join(secrets.choice(alphabet) for _ in range(7)),
    "".join(secrets.choice(password) for _ in range(8)),
    "".join(secrets.choice(alphabet) for _ in range(7)),
    "".join(secrets.choice(password) for _ in range(8)),
]
if values[0] == values[2]:
    raise SystemExit("generated duplicate SSIDs")
print(*values, sep="\n")
PY
}

take_device() {
  local ack="${1:-}"
  local mode="${3:-unchanged}"
  local expected_ack run_label
  case "$mode" in
    unchanged)
      expected_ack=TAKE-H6199-CONTROL
      run_label="RUN A"
      ;;
    mutate-mqtt)
      expected_ack=TAKE-H6199-RUN-B
      run_label="RUN B"
      ;;
    probe-client-hello)
      expected_ack=TAKE-H6199-RUN-C
      run_label="RUN C"
      ;;
    capture-mqtt-connect)
      expected_ack=TAKE-H6199-RUN-D
      run_label="RUN D"
      ;;
    *)
      echo "unsupported run mode" >&2
      return 2
      ;;
  esac
  active_run_id="${2:-run-${mode}-$(date +%Y%m%d-%H%M%S)}"
  [ "$ack" = "$expected_ack" ] || {
    echo "take-device requires acknowledgement $expected_ack" >&2
    return 2
  }
  [ -s "$baseline_marker" ] || {
    echo "baseline marker is absent; calibration/version power-cycle proof must run first" >&2
    return 1
  }
  load_identity
  mapfile -t generated < <(generate_credentials)
  [ "${#generated[@]}" = 4 ] || {
    echo "credential generation failed" >&2
    return 1
  }
  lab_ssid="${generated[0]}"
  lab_passphrase="${generated[1]}"
  restore_ssid="${generated[2]}"
  restore_passphrase="${generated[3]}"
  active_unifi_state="$live_dir/unifi-$active_run_id.json"
  relay_events="$live_dir/events-$active_run_id.jsonl"
  lab_log="$live_dir/provision-lab-$active_run_id.txt"
  restore_log="$live_dir/provision-restore-$active_run_id.txt"
  ble_write_intent="$live_dir/ble-write-intent-$active_run_id"
  rm -f "$ble_write_intent"
  network_attempted=0
  device_touched=0
  relay_intended=0
  swap_intended=0
  restored=0
  ha_release_intended=0

  cleanup() {
    local status=$?
    if [ -n "$ble_write_intent" ] && [ -e "$ble_write_intent" ]; then
      device_touched=1
    fi
    if [ "$ha_release_intended" = 1 ]; then
      ha_enable >/dev/null 2>&1 || true
    fi
    if [ "$relay_intended" = 1 ]; then
      proxmox stop "$active_run_id" >/dev/null 2>&1 || true
    fi
    if [ -e "$active_unifi_state" ]; then
      if [ "$device_touched" = 0 ] || [ "$restored" = 1 ]; then
        unifi_command teardown --state "$active_unifi_state" >/dev/null 2>&1 || true
      else
        echo "RECOVERY OUTSTANDING: isolated UniFi resources were intentionally retained." >&2
      fi
    elif [ "$network_attempted" = 1 ]; then
      echo "CHECK UNIFI: apply failed before local ownership state was confirmed." >&2
    fi
    if [ "$swap_intended" = 1 ]; then
      proxmox swap-restore >/dev/null 2>&1 || true
    fi
    unset lab_passphrase restore_passphrase
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  network_attempted=1
  printf '%s\n%s\n%s\n%s\n' \
    "$lab_ssid" "$lab_passphrase" \
    "$restore_ssid" "$restore_passphrase" |
    unifi_command apply \
      --ack APPLY-RUN-A-ISOLATION \
      --run-id "$active_run_id" \
      --relay-ip 192.168.0.167 \
      --vlan 30 \
      --state "$active_unifi_state"
  unifi_command status --state "$active_unifi_state" | grep -q '"ready": true'

  swap_intended=1
  proxmox swap-off
  proxmox deploy
  relay_intended=1
  proxmox start "$active_run_id" "$mode"
  sleep 2
  proxmox probe-local "$active_run_id"

  ha_release_intended=1
  ha_disable
  sleep 4
  printf '%s\n%s\n%s\n' \
    "$lab_ssid" "$lab_passphrase" "https://govee.ai.xaz.lol" |
    BLE_WRITE_INTENT_PATH="$ble_write_intent" windows_ble provision >"$lab_log"
  device_touched=1
  ha_enable
  ha_release_intended=0
  chmod 600 "$lab_log"
  grep -Eq 'NOTIFY.*a11100' "$lab_log"
  unifi_command wait-client \
    --state "$active_unifi_state" \
    --role lab \
    --timeout-seconds 30

  proxmox wait "$active_run_id"
  relay_intended=0
  proxmox events "$active_run_id" >"$relay_events"
  chmod 600 "$relay_events"
  grep -q '"event":"upstream_fetched"' "$relay_events"
  grep -q '"event":"response_relayed"' "$relay_events"

  ha_release_intended=1
  ha_disable
  sleep 4
  printf '%s\n%s\n%s\n' \
    "$restore_ssid" "$restore_passphrase" "https://device.govee.com" |
    windows_ble provision >"$restore_log"
  ha_enable
  ha_release_intended=0
  chmod 600 "$restore_log"
  grep -Eq 'NOTIFY.*a11100' "$restore_log"
  unifi_command wait-client \
    --state "$active_unifi_state" \
    --role restore \
    --timeout-seconds 30
  ha_wait_loaded
  restored=1

  unifi_command teardown --state "$active_unifi_state"
  network_attempted=0
  proxmox swap-restore
  swap_intended=0
  rm -f "$ble_write_intent"
  trap - EXIT INT TERM

  if [ "$mode" != unchanged ]; then
    grep -q '"event":"response_mutated"' "$relay_events"
  fi
  if [ "$mode" = probe-client-hello ]; then
    grep -q '"event":"mqtt_client_hello"' "$relay_events"
  fi
  if [ "$mode" = capture-mqtt-connect ]; then
    grep -q '"event":"mqtt_tls_accepted"' "$relay_events"
    grep -q '"event":"mqtt_connect_shape"' "$relay_events"
  fi

  if grep -q '"event":"dns_match"' "$relay_events"; then
    if [ "$mode" = capture-mqtt-connect ]; then
      echo "$run_label SUCCESS: controlled TLS endpoint received MQTT CONNECT."
    elif [ "$mode" = probe-client-hello ]; then
      echo "$run_label SUCCESS: controlled endpoint received a TLS ClientHello."
    elif [ "$mode" = mutate-mqtt ]; then
      echo "$run_label SUCCESS: mutated mqttAddress produced nonce DNS."
    else
      echo "$run_label SUCCESS: unchanged response produced attributable next-stage DNS."
    fi
    echo "Terminal state: the H6199 is provisioned to a retired absent restore SSID."
  else
    echo "$run_label RELAYED: no attributable next-stage DNS was observed."
    echo "Terminal state: the H6199 is provisioned to a retired absent restore SSID."
    return 1
  fi
}

restore_only() {
  local ack="${1:-}"
  local run_id="${2:?run ID required}"
  local state="$live_dir/unifi-$run_id.json"
  local restore_log="$live_dir/provision-restore-$run_id.txt"
  local write_intent="$live_dir/ble-write-intent-$run_id"
  local restore_ssid restore_passphrase
  [ "$ack" = RESTORE-H6199-NOW ] || {
    echo "restore requires acknowledgement RESTORE-H6199-NOW" >&2
    return 2
  }
  [ -s "$state" ] || {
    echo "retained UniFi state is absent" >&2
    return 1
  }
  load_identity
  restore_ssid="$("$python" -c '
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
print(value["restore_wlan"]["name"])
' "$state")"
  restore_passphrase="$("$python" - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(8)))
PY
)"

  cleanup_restore() {
    local status=$?
    if [ "$ha_release_intended" = 1 ]; then
      ha_enable >/dev/null 2>&1 || true
    fi
    unset restore_passphrase
    if [ "$status" -ne 0 ]; then
      echo "RECOVERY OUTSTANDING: isolated UniFi resources were retained." >&2
    fi
    exit "$status"
  }
  trap cleanup_restore EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM

  printf '%s\n' "$restore_passphrase" |
    unifi_command rotate-restore --state "$state" >/dev/null
  sleep 5
  ha_release_intended=1
  ha_disable
  sleep 4
  printf '%s\n%s\n%s\n' \
    "$restore_ssid" "$restore_passphrase" "https://device.govee.com" |
    BLE_WRITE_INTENT_PATH="$write_intent" windows_ble provision >"$restore_log"
  ha_enable
  ha_release_intended=0
  chmod 600 "$restore_log"
  grep -Eq 'NOTIFY.*a11100' "$restore_log"
  unifi_command wait-client \
    --state "$state" \
    --role restore \
    --timeout-seconds 60
  ha_wait_loaded
  unifi_command teardown --state "$state"
  rm -f "$write_intent"
  unset restore_passphrase
  trap - EXIT INT TERM
  echo "RESTORE COMPLETE: the H6199 is provisioned to a retired absent restore SSID."
}

case "${1:-}" in
  preflight) preflight "${2:-}" ;;
  take-device) take_device "${2:-}" "${3:-}" unchanged ;;
  take-device-b) take_device "${2:-}" "${3:-}" mutate-mqtt ;;
  take-device-c) take_device "${2:-}" "${3:-}" probe-client-hello ;;
  take-device-d) take_device "${2:-}" "${3:-}" capture-mqtt-connect ;;
  restore) restore_only "${2:-}" "${3:-}" ;;
  *)
    echo "usage: $0 preflight [RUN_ID] | take-device TAKE-H6199-CONTROL [RUN_ID] | take-device-b TAKE-H6199-RUN-B [RUN_ID] | take-device-c TAKE-H6199-RUN-C [RUN_ID] | take-device-d TAKE-H6199-RUN-D [RUN_ID] | restore RESTORE-H6199-NOW RUN_ID" >&2
    exit 2
    ;;
esac
