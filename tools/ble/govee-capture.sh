#!/usr/bin/env bash
# Efficient Govee BLE capture loop, driven from WSL via pwsh.exe.
#
#   govee-capture.sh start <name>   # begin capture, then do ONE action in the app
#   govee-capture.sh stop           # stop the running capture and decode it
#   govee-capture.sh decode <name>  # re-decode an existing capture
#   govee-capture.sh list           # list captures
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
    [ ! -f "$STATE" ] || { echo "a capture is already running"; exit 1; }
    name="${name//[^A-Za-z0-9._-]/_}"
    mkdir -p "$CAP"
    out="$WIN_CAP/${name}.pcap"
    pid="$("$PWSH" -NoProfile -Command "\$p = Start-Process -FilePath '$EXE' -ArgumentList '-f','pcap','$out' -WindowStyle Hidden -PassThru; \$p.Id" | tr -d '\r[:space:]')"
    started_at="$(date --iso-8601=seconds)"
    printf '%s %s %s\n' "$pid" "$name" "$started_at" > "$STATE"
    for _ in {1..20}; do
      [ -f "$CAP/$name.pcap" ] && [ "$(stat -c %s "$CAP/$name.pcap")" -ge 24 ] && break
      sleep 0.25
    done
    if [ ! -f "$CAP/$name.pcap" ] || [ "$(stat -c %s "$CAP/$name.pcap")" -lt 24 ]; then
      "$PWSH" -NoProfile -Command "Stop-Process -Id $pid -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
      rm -f "$STATE"
      echo "capture preflight failed: idevicebtlogger wrote no pcap header" >&2
      exit 1
    fi
    echo "recording '$name' (pid $pid)"
    echo ">> perform ONE action in the Govee app now, then: govee-capture.sh stop"
    ;;
  stop)
    [ -f "$STATE" ] || { echo "no capture running"; exit 1; }
    read -r pid name started_at < "$STATE"
    "$PWSH" -NoProfile -Command "Stop-Process -Id $pid -ErrorAction SilentlyContinue" >/dev/null 2>&1 || true
    sleep 0.4
    rm -f "$STATE"
    stopped_at="$(date --iso-8601=seconds)"
    printf '{"capture":"%s","started_at":"%s","stopped_at":"%s"}\n' \
      "$name" "$started_at" "$stopped_at" > "$CAP/$name.meta.json"
    echo "stopped '$name' (pid $pid)"
    python3 "$SELF_DIR/decode_govee.py" "$CAP/$name.pcap"
    ;;
  decode)
    name="${2:-}"; [ -n "$name" ] || usage 1
    shift 2
    python3 "$SELF_DIR/decode_govee.py" "$CAP/$name.pcap" "$@"
    ;;
  list)
    ls -lh "$CAP"/*.pcap 2>/dev/null || echo "no captures yet"
    ;;
  *)
    usage 0 ;;
esac
