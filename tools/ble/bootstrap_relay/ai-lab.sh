#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
container=105
remote_root=/root/govee-relay-mvp
live_root=/root/govee-relay-live
harness_repo=/workspaces/ha-govee-led-ble
python=/home/lab/ha-govee-led-ble/.venv/bin/python

umask 077
config="$(mktemp)"
archive=""
cleanup() {
  rm -f "$config"
  [ -z "$archive" ] || rm -f "$archive"
}
trap cleanup EXIT

printf 'Host platform\n  HostName %s\n  User %s\n  BatchMode yes\n' \
  "$PROXMOX_SSH_HOST" "$PROXMOX_SSH_USER" >"$config"

remote() {
  ssh -F "$config" -o StrictHostKeyChecking=accept-new platform "$@"
}

valid_run_id() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,23}$ ]]
}

deploy() {
  remote "pct exec $container -- runuser -u lab -- git -C $harness_repo pull --ff-only"
  archive="$(mktemp)"
  tar -C "$root" \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='.mypy_cache' \
    --exclude='evidence' \
    --exclude='live' \
    -cf "$archive" \
    govee_relay tests pyproject.toml run-tests.sh \
    ai-lab.sh baseline.sh ha-platform.sh rehearse-infra.sh run-a.sh \
    windows-ble.sh README.md THREAT-MODEL.md RUN-A.md REQUEST-FINGERPRINT.md
  remote "pct exec $container -- rm -rf $remote_root &&
    pct exec $container -- install -d -m 700 $remote_root &&
    pct exec $container -- tar -C $remote_root -xf -" <"$archive"
  remote "pct exec $container -- find $remote_root -type d -exec chmod 700 {} +;
    pct exec $container -- find $remote_root -type f -exec chmod 600 {} +;
    pct exec $container -- chmod 700 $remote_root/run-tests.sh"
}

test_tooling() {
  remote "pct exec $container -- bash -lc '
    set -euo pipefail
    cd $remote_root
    export PYTHONPATH=.
    export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    export PYTHONDONTWRITEBYTECODE=1
    $python -m pytest -p no:cacheprovider --tb=short -q
    $python -m ruff check .
    $python -m ruff format --check .
    $python -m mypy --cache-dir=/dev/null govee_relay tests
  '"
}

preflight() {
  remote "pct exec $container -- bash -lc '
    if ss -H -lntu | awk \"{print \\\$5}\" | grep -Eq \":(53|123|443)\\$\"; then
      echo \"required relay port is already in use\" >&2
      exit 1
    fi
    install -d -m 700 $live_root/preflight
    cd $remote_root
    export PYTHONPATH=.
    $python -m govee_relay.live check \
      --device-host govee.ai.xaz.lol \
      --work-dir $live_root/preflight \
      --production-tls
  '"
}

swap_off() {
  remote "
    set -eu
    test ! -e /root/govee-relay-swap.previous
    previous=\$(pct config $container | sed -n 's/^swap: //p')
    printf '%s\n' \"\${previous:-0}\" >/root/govee-relay-swap.previous
    chmod 600 /root/govee-relay-swap.previous
    pct set $container -swap 0
    pct reboot $container
    for attempt in \$(seq 1 30); do
      sleep 2
      pct exec $container -- true 2>/dev/null && break
      test \"\$attempt\" -lt 30
    done
    pct exec $container -- awk '/^SwapTotal:/ { if (\$2 != 0) exit 1 }' /proc/meminfo
  "
}

swap_restore() {
  remote "
    set -eu
    if test -s /root/govee-relay-swap.previous; then
      previous=\$(cat /root/govee-relay-swap.previous)
      pct set $container -swap \"\$previous\"
      rm -f /root/govee-relay-swap.previous
    fi
  "
}

start_relay() {
  local run_id="${1:?run ID required}"
  local mode="${2:-unchanged}"
  local ack mutation_args
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  case "$mode" in
    unchanged)
      ack=UNCHANGED-PRODUCTION-RELAY
      mutation_args=""
      ;;
    mutate-mqtt)
      ack=MUTATE-MQTT-ADDRESS-ONLY
      mutation_args="--mqtt-address-nonce $run_id.nonce.govee.ai.xaz.lol --stop-on-dns-match"
      ;;
    probe-client-hello)
      ack=MUTATE-MQTT-ADDRESS-ONLY
      mutation_args="--mqtt-address-nonce $run_id.nonce.govee.ai.xaz.lol --mqtt-probe-port 8883"
      ;;
    capture-mqtt-connect)
      ack=MUTATE-MQTT-ADDRESS-ONLY
      mutation_args="--mqtt-address-nonce $run_id.nonce.govee.ai.xaz.lol --mqtt-probe-port 8883 --capture-mqtt-connect"
      ;;
    *)
      echo "unsupported relay mode" >&2
      return 2
      ;;
  esac
  remote "pct exec $container -- bash -lc '
    run_dir=$live_root/$run_id
    test ! -e \"\$run_dir\"
    install -d -m 700 \"\$run_dir\"
    cd $remote_root
    export PYTHONPATH=.
    nohup $python -m govee_relay.live run \
      --ack $ack \
      --run-id $run_id \
      --device-host govee.ai.xaz.lol \
      --relay-ip 192.168.0.167 \
      --work-dir \"\$run_dir\" \
      --event-path \"\$run_dir/events.jsonl\" \
      --state-path \"\$run_dir/state.json\" \
      --deadline-seconds 180 \
      --prewarm-refresh-seconds 3 \
      $mutation_args \
      >\"\$run_dir/launch.log\" 2>&1 &
    printf \"%s\n\" \"\$!\" >\"\$run_dir/launcher.pid\"
    chmod 600 \"\$run_dir/launcher.pid\"
    for attempt in \$(seq 1 50); do
      test -s \"\$run_dir/state.json\" && exit 0
      if ! kill -0 \"\$(cat \"\$run_dir/launcher.pid\")\" 2>/dev/null; then
        exit 1
      fi
      sleep 0.1
    done
    exit 1
  '"
}

stop_relay() {
  local run_id="${1:?run ID required}"
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  remote "pct exec $container -- bash -lc '
    run_dir=$live_root/$run_id
    if test -s \"\$run_dir/state.json\"; then
      cd $remote_root
      export PYTHONPATH=.
      $python -m govee_relay.live stop --state-path \"\$run_dir/state.json\" || true
    elif test -s \"\$run_dir/launcher.pid\"; then
      pid=\$(cat \"\$run_dir/launcher.pid\")
      kill \"\$pid\" 2>/dev/null || true
    fi
  '"
}

wait_relay() {
  local run_id="${1:?run ID required}"
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  remote "pct exec $container -- bash -lc '
    run_dir=$live_root/$run_id
    test -s \"\$run_dir/launcher.pid\"
    pid=\$(cat \"\$run_dir/launcher.pid\")
    for attempt in \$(seq 1 1050); do
      ! kill -0 \"\$pid\" 2>/dev/null && exit 0
      sleep 0.2
    done
    echo \"relay did not stop within 210 seconds\" >&2
    exit 1
  '"
}

events() {
  local run_id="${1:?run ID required}"
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  remote "pct exec $container -- cat $live_root/$run_id/events.jsonl"
}

launch_log() {
  local run_id="${1:?run ID required}"
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  remote "pct exec $container -- cat $live_root/$run_id/launch.log"
}

probe_local() {
  local run_id="${1:?run ID required}"
  valid_run_id "$run_id" || { echo "invalid run ID" >&2; return 2; }
  remote "pct exec $container -- bash -lc '
    set -euo pipefail
    answer=\$(dig @127.0.0.1 +time=2 +tries=1 +short govee.ai.xaz.lol A)
    test \"\$answer\" = 192.168.0.167
    dig @127.0.0.1 +time=2 +tries=1 govee.ai.xaz.lol AAAA |
      grep -q \"status: NOERROR\"
    python3 - <<'\''PY'\''
import socket

request = bytearray(48)
request[0] = 0x23
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(2)
    client.sendto(request, (\"127.0.0.1\", 123))
    response, _address = client.recvfrom(512)
if len(response) != 48 or response[0] & 0x07 != 4:
    raise SystemExit(\"invalid NTP response\")
PY
    tls=\$(timeout 5 openssl s_client \
      -connect 127.0.0.1:443 \
      -servername govee.ai.xaz.lol \
      -tls1_2 \
      -cipher AES256-SHA256 \
      -brief </dev/null 2>&1 || true)
    grep -q \"Protocol version: TLSv1.2\" <<<\"\$tls\"
    grep -q \"Ciphersuite: AES256-SHA256\" <<<\"\$tls\"
    echo \"local relay DNS NTP and TLS probe passed\"
  '"
}

stdin_probe() {
  remote "pct exec $container -- python3 -c '
import json
import sys

lines = sys.stdin.read().splitlines()
print(json.dumps({\"line_count\": len(lines), \"lengths\": [len(line) for line in lines]}))
'"
}

case "${1:-}" in
  deploy) deploy ;;
  test) test_tooling ;;
  preflight) preflight ;;
  harness-preflight) harness_preflight ;;
  swap-off) swap_off ;;
  swap-restore) swap_restore ;;
  start) start_relay "${2:-}" "${3:-unchanged}" ;;
  stop) stop_relay "${2:-}" ;;
  wait) wait_relay "${2:-}" ;;
  events) events "${2:-}" ;;
  launch-log) launch_log "${2:-}" ;;
  probe-local) probe_local "${2:-}" ;;
  stdin-probe) stdin_probe ;;
  *)
    echo "usage: $0 deploy|test|preflight|swap-off|swap-restore|start RUN [unchanged|mutate-mqtt|probe-client-hello|capture-mqtt-connect]|stop RUN|wait RUN|events RUN|launch-log RUN|probe-local RUN|stdin-probe" >&2
    exit 2
    ;;
esac
