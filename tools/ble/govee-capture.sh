#!/usr/bin/env bash
# Efficient Govee BLE capture loop, driven from WSL via pwsh.exe.
#
#   govee-capture.sh start <name> [prediction-sha256]  # begin capture
#   govee-capture.sh mark <label>    # timestamp an action in a batched capture
#   govee-capture.sh stop            # stop the running capture and decode it
#   govee-capture.sh decode <name>   # re-decode an existing capture
#   govee-capture.sh list            # list captures
#
# Captures stream to $GOVEE_BLE_DIR/captures/<name>.pcap. Stop is by PID, so you tap
# the app at your own pace (idevicebtlogger has no duration flag and Ctrl+C cannot be
# delivered to a Windows process from WSL).
#
# Required env: GOVEE_BLE_DIR (WSL path to the tooling dir), GOVEE_WIN_CAP
# (Windows capture directory), GOVEE_BTLOGGER (Windows idevicebtlogger.exe).
# Optional env: PWSH (PowerShell executable, default pwsh.exe).
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SELF_DIR/../.." && pwd)"
: "${GOVEE_BLE_DIR:?set GOVEE_BLE_DIR to the WSL capture-tool directory}"
: "${GOVEE_WIN_CAP:?set GOVEE_WIN_CAP to the Windows capture directory}"
: "${GOVEE_BTLOGGER:?set GOVEE_BTLOGGER to idevicebtlogger.exe}"
DIR="$GOVEE_BLE_DIR"
CAP="$DIR/captures"
WIN_CAP="$GOVEE_WIN_CAP"
STATE="$CAP/.current"
EXE="$GOVEE_BTLOGGER"
PWSH="${PWSH:-pwsh.exe}"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

case "${1:-}" in
  start)
    name="${2:-}"; [ -n "$name" ] || usage 1
    prediction_sha256="${3:--}"
    if [ "$prediction_sha256" != "-" ] && [[ ! "$prediction_sha256" =~ ^[0-9a-f]{64}$ ]]; then
      echo "prediction SHA-256 must be 64 lowercase hexadecimal characters" >&2
      exit 1
    fi
    # Fresh start: stop any previous capture (stale or running) and clear its state.
    if [ -f "$STATE" ]; then
      read -r old_pid old_name _ < "$STATE" || true
      echo "clearing previous capture '${old_name:-?}' (pid ${old_pid:-?})" >&2
      [ -n "${old_pid:-}" ] && "$PWSH" -NoProfile -Command "Stop-Process -Id $old_pid -Force -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
      rm -f "$STATE"
    fi
    # idevicebtlogger allows only one client on the packet-logger service; orphaned
    # instances (e.g. a wrapper killed by 'timeout') leave it held, so every new
    # capture writes 0 bytes. Clear stray loggers so each effort starts fresh.
    "$PWSH" -NoProfile -Command "Get-Process idevicebtlogger -ErrorAction SilentlyContinue | Stop-Process -Force" >/dev/null 2>&1 || true
    name="${name//[^A-Za-z0-9._-]/_}"
    mkdir -p "$CAP"
    out="$WIN_CAP/${name}.pcap"
    pid="$("$PWSH" -NoProfile -Command "\$p = Start-Process -FilePath '$EXE' -ArgumentList '-f','pcap','$out' -WindowStyle Hidden -PassThru; \$p.Id" | tr -d '\r[:space:]')"
    started_at="$(date --iso-8601=ns)"
    printf '%s %s %s %s\n' "$pid" "$name" "$started_at" "$prediction_sha256" > "$STATE"
    : > "$CAP/$name.actions.tsv"
    for _ in {1..20}; do
      [ -f "$CAP/$name.pcap" ] && [ "$(stat -c %s "$CAP/$name.pcap")" -ge 24 ] && break
      sleep 0.25
    done
    if [ ! -f "$CAP/$name.pcap" ] || [ "$(stat -c %s "$CAP/$name.pcap")" -lt 24 ]; then
      "$PWSH" -NoProfile -Command "Stop-Process -Id $pid -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
      rm -f "$STATE" "$CAP/$name.actions.tsv"
      echo "capture preflight failed: idevicebtlogger connected but wrote no pcap header" >&2
      echo "  the phone's HCI stream is not flowing. Check, in order:" >&2
      echo "  1. the iPhone is unlocked;" >&2
      echo "  2. the Bluetooth logging (PacketLogger) profile is still installed and valid;" >&2
      echo "  3. toggle Bluetooth off then on to restart the HCI stream." >&2
      exit 1
    fi
    echo "recording '$name' (pid $pid)"
    echo ">> mark each batched action immediately before it starts, then run: govee-capture.sh stop"
    ;;
  mark)
    [ -f "$STATE" ] || { echo "no capture running"; exit 1; }
    shift
    label="$*"; [ -n "$label" ] || usage 1
    read -r _ name _ < "$STATE"
    label="${label//$'\t'/ }"
    label="${label//$'\r'/ }"
    label="${label//$'\n'/ }"
    printf '%s\t%s\n' "$(date --iso-8601=ns)" "$label" >> "$CAP/$name.actions.tsv"
    echo "marked '$label'"
    ;;
  stop)
    [ -f "$STATE" ] || { echo "no capture running"; exit 1; }
    read -r pid name started_at prediction_sha256 < "$STATE"
    prediction_sha256="${prediction_sha256:--}"
    "$PWSH" -NoProfile -Command "Stop-Process -Id $pid -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
    sleep 0.4
    rm -f "$STATE"
    stopped_at="$(date --iso-8601=ns)"
    if [ "$prediction_sha256" = "-" ]; then
      prediction_json=null
    else
      prediction_json="\"$prediction_sha256\""
    fi
    printf '{"capture":"%s","started_at":"%s","stopped_at":"%s","actions":"%s.actions.tsv","prediction_sha256":%s}\n' \
      "$name" "$started_at" "$stopped_at" "$name" "$prediction_json" > "$CAP/$name.meta.json"
    echo "stopped '$name' (pid $pid)"
    uv run --project "$PROJECT_DIR" python "$SELF_DIR/decode_govee.py" "$CAP/$name.pcap"
    ;;
  decode)
    name="${2:-}"; [ -n "$name" ] || usage 1
    shift 2
    uv run --project "$PROJECT_DIR" python "$SELF_DIR/decode_govee.py" "$CAP/$name.pcap" "$@"
    ;;
  list)
    ls -lh "$CAP"/*.pcap 2>/dev/null || echo "no captures yet"
    ;;
  *)
    usage 0 ;;
esac
