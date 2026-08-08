#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO_DIR:-$HOME/ha-govee-led-ble}"
platform_helper="${BWS_PLATFORM_HELPER:-$HOME/.copilot/skills/platform/scripts/platform-bws.sh}"
python="$repo/.venv/bin/python"
run_id="infra-$(date +%H%M%S)"
state="$root/live/unifi-$run_id.json"
events="$root/live/events-$run_id.jsonl"
network_attempted=0
relay_intended=0
swap_intended=0

umask 077
mkdir -p "$root/live"
chmod 700 "$root/live"

unifi() {
  bash "$platform_helper" run UNIFI -- bash -lc "$1"
}

proxmox() {
  bash "$platform_helper" run PROXMOX -- bash "$root/ai-lab.sh" "$@"
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

cleanup() {
  local status=$?
  if [ "$relay_intended" = 1 ]; then
    proxmox stop "$run_id" >/dev/null 2>&1 || true
  fi
  if [ -e "$state" ]; then
    unifi_command teardown --state "$state" >/dev/null 2>&1 || true
  elif [ "$network_attempted" = 1 ]; then
    echo "CHECK UNIFI: rehearsal apply left no local ownership state." >&2
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

mapfile -t generated < <(
  "$python" - <<'PY'
import secrets
import string

alphabet = string.ascii_uppercase + string.digits
password = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(7)))
print("".join(secrets.choice(password) for _ in range(8)))
print("".join(secrets.choice(alphabet) for _ in range(7)))
print("".join(secrets.choice(password) for _ in range(8)))
PY
)
lab_ssid="${generated[0]}"
lab_passphrase="${generated[1]}"
restore_ssid="${generated[2]}"
restore_passphrase="${generated[3]}"

network_attempted=1
printf '%s\n%s\n%s\n%s\n' \
  "$lab_ssid" "$lab_passphrase" \
  "$restore_ssid" "$restore_passphrase" |
  unifi_command apply \
    --ack APPLY-RUN-A-ISOLATION \
    --run-id "$run_id" \
    --relay-ip 192.168.0.167 \
    --vlan 30 \
    --state "$state"
unifi_command status --state "$state" | grep -q '"ready": true'

swap_intended=1
proxmox swap-off
proxmox deploy
relay_intended=1
proxmox start "$run_id"
sleep 2
proxmox probe-local "$run_id"
proxmox stop "$run_id"
proxmox wait "$run_id"
relay_intended=0
proxmox events "$run_id" >"$events"
chmod 600 "$events"
if grep -q '"event":"upstream_fetched"' "$events"; then
  echo "rehearsal unexpectedly sent an upstream HTTP request" >&2
  exit 1
fi
if grep -q '"event":"response_schema"' "$events"; then
  echo "rehearsal unexpectedly received a production response" >&2
  exit 1
fi

unifi_command teardown --state "$state"
network_attempted=0
proxmox swap-restore
swap_intended=0
trap - EXIT INT TERM
unset lab_passphrase restore_passphrase
echo "Infrastructure rehearsal passed and all temporary state was removed."
