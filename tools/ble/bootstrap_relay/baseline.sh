#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="${REPO_DIR:-$HOME/ha-govee-led-ble}"
platform_helper="${BWS_PLATFORM_HELPER:-$HOME/.copilot/skills/platform/scripts/platform-bws.sh}"
python="$repo/.venv/bin/python"
identity="$repo/tools/harness/devices.local.env"
live_dir="$root/live"
marker="$live_dir/baseline-passed.json"
ha_release_intended=0

umask 077
mkdir -p "$live_dir"
chmod 700 "$live_dir"

source "$identity"
entry_id="${DEVICE_HA_ENTRY[dreamtv]}"

ha_action() {
  local action=$1
  printf '%s\n' "$entry_id" |
    bash "$platform_helper" run HA -- bash "$root/ha-platform.sh" "$action" "$repo"
}

ha_disable() {
  ha_action disable | grep -qi '"success": true'
}

ha_enable() {
  ha_action enable | grep -qi '"success": true'
}

baseline_cleanup() {
  [ "$ha_release_intended" = 0 ] || ha_enable >/dev/null 2>&1 || true
}

query_versions() {
  local output=$1
  trap baseline_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  ha_release_intended=1
  ha_disable
  sleep 4
  bash "$root/windows-ble.sh" query-versions |
    sed -nE "s/.*(reply (firmware|hardware|subordinate_20|subordinate_21)='[^']+').*/\\1/p" |
    sort -u >"$output"
  chmod 600 "$output"
  ha_enable
  ha_release_intended=0
  trap - EXIT INT TERM
  [ "$(wc -l <"$output")" = 4 ] || {
    echo "did not receive all four version canaries" >&2
    return 1
  }
}

capture() {
  local phase="${1:?before or after required}"
  case "$phase" in before|after) ;; *) echo "phase must be before or after" >&2; return 2 ;; esac
  if [ "$phase" = after ]; then
    [ "${2:-}" = POWER-CYCLE-COMPLETED ] || {
      echo "after capture requires acknowledgement POWER-CYCLE-COMPLETED" >&2
      return 2
    }
    [ -s "$live_dir/version-before.txt" ] && [ -s "$live_dir/capture-before.at" ] || {
      echo "before capture is absent" >&2
      return 1
    }
  else
    rm -f "$marker" "$live_dir/version-after.txt" "$live_dir/capture-after.at"
  fi
  query_versions "$live_dir/version-$phase.txt"
  date -Is >"$live_dir/capture-$phase.at"
  chmod 600 "$live_dir/capture-$phase.at"
  echo "Captured $phase version canaries. Photograph the fixed HDMI calibration pattern now."
}

approve() {
  local ack="${1:-}"
  local before_photo="${2:-}"
  local after_photo="${3:-}"
  [ "$ack" = CALIBRATION-UNCHANGED ] || {
    echo "approve requires acknowledgement CALIBRATION-UNCHANGED" >&2
    return 2
  }
  [ -s "$live_dir/version-before.txt" ] && [ -s "$live_dir/version-after.txt" ] || {
    echo "before and after version captures are required" >&2
    return 1
  }
  cmp -s "$live_dir/version-before.txt" "$live_dir/version-after.txt" || {
    echo "version canaries changed across the power cycle" >&2
    return 1
  }
  [ -s "$before_photo" ] && [ -s "$after_photo" ] || {
    echo "before and after calibration photographs are required" >&2
    return 1
  }
  [ "$before_photo" != "$after_photo" ] || {
    echo "before and after photographs must be different files" >&2
    return 1
  }
  [ -s "$live_dir/capture-before.at" ] && [ -s "$live_dir/capture-after.at" ] || {
    echo "capture timestamps are required" >&2
    return 1
  }
  BEFORE_PHOTO="$before_photo" AFTER_PHOTO="$after_photo" LIVE_DIR="$live_dir" \
    "$python" - <<'PY' >"$marker"
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path


def digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


live = Path(os.environ["LIVE_DIR"])
before_digest = digest(os.environ["BEFORE_PHOTO"])
after_digest = digest(os.environ["AFTER_PHOTO"])
if before_digest == after_digest:
    raise SystemExit("before and after photographs have identical content")
print(json.dumps({
    "approved_at": datetime.now(UTC).isoformat(),
    "calibration_visual_verdict": "unchanged",
    "power_cycle_acknowledged": True,
    "before_captured_at": (live / "capture-before.at").read_text().strip(),
    "after_captured_at": (live / "capture-after.at").read_text().strip(),
    "before_photo_sha256": before_digest,
    "after_photo_sha256": after_digest,
    "version_canaries_sha256": digest(str(live / "version-before.txt")),
}, sort_keys=True))
PY
  chmod 600 "$marker"
  echo "Baseline gate passed."
}

waive_calibration() {
  local ack="${1:-}"
  [ "$ack" = ACCEPT-CALIBRATION-RESET-RISK ] || {
    echo "waive requires acknowledgement ACCEPT-CALIBRATION-RESET-RISK" >&2
    return 2
  }
  [ -s "$live_dir/version-before.txt" ] && [ -s "$live_dir/capture-before.at" ] || {
    echo "before version capture is required" >&2
    return 1
  }
  LIVE_DIR="$live_dir" "$python" - <<'PY' >"$marker"
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path


live = Path(os.environ["LIVE_DIR"])
version = live / "version-before.txt"
print(json.dumps({
    "approved_at": datetime.now(UTC).isoformat(),
    "calibration_visual_verdict": "unverified_risk_accepted",
    "power_cycle_acknowledged": False,
    "before_captured_at": (live / "capture-before.at").read_text().strip(),
    "version_canaries_sha256": hashlib.sha256(version.read_bytes()).hexdigest(),
}, sort_keys=True))
PY
  chmod 600 "$marker"
  echo "Baseline gate passed with calibration-reset risk accepted."
}

case "${1:-}" in
  capture) capture "${2:-}" "${3:-}" ;;
  approve) approve "${2:-}" "${3:-}" "${4:-}" ;;
  waive) waive_calibration "${2:-}" ;;
  *)
    echo "usage: $0 capture before | capture after POWER-CYCLE-COMPLETED | approve CALIBRATION-UNCHANGED BEFORE_PHOTO AFTER_PHOTO | waive ACCEPT-CALIBRATION-RESET-RISK" >&2
    exit 2
    ;;
esac
