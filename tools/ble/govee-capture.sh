#!/usr/bin/env bash
# Govee BLE capture, driven through the phone's native USB owner.
#
# Not executable by design, like every script here, so it is invoked through bash. The
# harness wraps it as capture(), which is what most callers should use.
#
#   bash tools/ble/govee-capture.sh start <name> [prediction-sha256]   begin capture
#   bash tools/ble/govee-capture.sh mark <label>                       timestamp an action
#   bash tools/ble/govee-capture.sh stop                               stop and decode
#   bash tools/ble/govee-capture.sh decode <name> [--all]
#   bash tools/ble/govee-capture.sh list
#
# NO TUNNEL IS NEEDED. com.apple.bluetooth.BTPacketLogger is a lockdown service, so this
# works over plain usbmux; only the app-driving half of the rig is behind RemoteXPC.
#
# Env: GOVEE_CAPTURE_DIR (default ~/govee-captures), PYMOBILEDEVICE3, IDEVICEBTLOGGER,
# PREFLIGHT_SECONDS. Set GOVEE_CAPTURE_BACKEND=idevicebtlogger for classic pcap from native
# WSL USB; the default remains pymobiledevice3 pcapng for the lab.
#
# GOVEE_EXPECTED_PEER is the BLE address the capture is SUPPOSED to be of. Set it and stop
# decodes only that peer and fails when the capture holds none of its frames. Without it a
# session where the app never reached the light produces a clean, empty-looking decode that
# reads as "the device said nothing", which is a conclusion rather than the error it is.
# up.sh sets it from the resolved device, so app-mode sessions get it for free.
#
# PUT THE PHONE IN AIRPLANE MODE, THEN TURN BLUETOOTH BACK ON, BEFORE CAPTURING. The vendor
# app prefers any IP path it has and only falls back to BLE, so a capture taken with the
# phone online UNDERSTATES the protocol instead of revealing it. Measured on the H6199
# 2026-08-03: with WiFi up the app asked aa 01 power and nothing else; offline, the same
# device page immediately asked aa 04 brightness, aa 05 colour mode, aa 11/aa 12/aa 23
# timers, aa a9 calibration and four groups of aa a5 segment colours. Airplane Mode rather
# than WiFi alone, because cellular keeps the cloud reachable, and Bluetooth back on because
# Airplane Mode takes it down with everything else. This costs nothing on a model with no
# IP path, so it is the default rather than a per-model step.
#
# TAKING THE DEVICE OFF WI-FI AS A SUBSTITUTE DOES NOT WORK, and the attempt is worth
# recording because it half-succeeds. On 2026-08-04 the H6199 was pushed credentials for a
# network that does not exist, first through the app and then by writing the same captured
# bytes directly from this host. Both times the device accepted the write, spent about
# eleven seconds trying, and reported failure on ee 11. It then went back to its stored
# network: with the phone online it still showed as cloud-reachable in the app's device
# list, beside two lights the same list marks "Device offline". A bad SSID is attempted and
# abandoned, not retained, so this is not a lever on the light's connectivity.
#
# The measurement that sat between those two facts proved less than it looked like.
# Phone-online captures do ask for less: opening the device page asked only the link and
# identity domains aa 01/06/07/14/20/21 and not aa 04, aa 05, aa 0f, aa 35, aa a5, aa a9 or
# aa ae, against a phone-offline control doing the same navigation that asked all of them.
# That was briefly written up as proof that the shortcut is phone-side and the light's own
# connectivity irrelevant. It is not proof of that: the light was reachable throughout, so
# the cheaper reading, that the app asked the cloud and the cloud asked a device that was
# up, was never excluded. The rule above stands on its own measurement, not on this one.
#
# THE EXCLUDING MEASUREMENT HAS NOW BEEN TAKEN, and it changes what the rule is ABOUT.
# On 2026-08-04 the H6199 was re-homed onto a throwaway network which was then deleted, so
# for the first time the light was genuinely associated to nothing: an independent check of
# the wireless controller showed it joined to no SSID at all, six minutes after the network
# it had committed to stopped existing. With the phone then taken OUT of Airplane Mode and
# back onto WiFi, opening the device page asked
#
#   aa 01 04 05 06 07 0f 11 12 14 20 21 23 35 a5 a9 ae
#
# which is the SAME SIXTEEN registers as a phone-offline control taken two hours earlier on
# the same device and app. Not a subset, not a superset: identical. So the app's shortcut is
# not phone-side at all. What matters is whether the DEVICE has an IP path, and Airplane Mode
# is merely the cheapest way to guarantee the app cannot use one.
#
# The rule therefore stays as written, because it is still the only thing that is true for
# every device and costs nothing. But it may be relaxed FOR A DEVICE PROVEN TO BE OFF THE
# NETWORK, and "proven" means checked against something other than the vendor app: its own
# device list was wrong about exactly this once already. A device that is merely believed to
# be offline, or that has been pushed credentials that failed, does not qualify — a failed
# push is attempted and abandoned, and the light returns to its stored network.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SELF_DIR/../.." && pwd)"
CAP="${GOVEE_CAPTURE_DIR:-$HOME/govee-captures}"
STATE="$CAP/.current"
PMD3="${PYMOBILEDEVICE3:-pymobiledevice3}"
IDEVICEBTLOGGER="${IDEVICEBTLOGGER:-idevicebtlogger}"
PREFLIGHT_SECONDS="${PREFLIGHT_SECONDS:-15}"
BACKEND="${GOVEE_CAPTURE_BACKEND:-native}"
BLUETOOTH_LOGGING_PROFILE_URL="${BLUETOOTH_LOGGING_PROFILE_URL:-https://secure-appldnld.apple.com/iOSProfiles/BluetoothLogging.mobileconfig}"
BLUETOOTH_LOGGING_PROFILE_UUID="${BLUETOOTH_LOGGING_PROFILE_UUID:-D8A1D847-C161-4D0A-9426-FB9C3E48297D}"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

stop_logger() {
  local pid=$1
  kill "$pid" 2>/dev/null || true
}

start_logger() {
  local out=$1 name=$2
  if [ "$BACKEND" = idevicebtlogger ]; then
    nohup "$IDEVICEBTLOGGER" -u "$PHONE_UDID" -f pcap -x "$out" >"$CAP/$name.log" 2>&1 &
    echo $!
    return
  fi
  # --format is not optional: the default is Apple's PacketLogger .pklg.
  # shellcheck disable=SC2046
  nohup "$PMD3" $(btlogger_argv) --format pcapng "$out" >"$CAP/$name.log" 2>&1 &
  echo $!
}

capture_suffix() {
  case "$BACKEND" in
    native) echo pcapng ;;
    idevicebtlogger) echo pcap ;;
    *)
      echo "unknown capture backend '$BACKEND'" >&2
      return 1
      ;;
  esac
}

capture_path() {
  local name=$1
  local suffix
  for suffix in pcap pcapng; do
    [ -f "$CAP/$name.$suffix" ] && {
      printf '%s\n' "$CAP/$name.$suffix"
      return 0
    }
  done
  echo "no capture named '$name'" >&2
  return 1
}

# 10.2.3 takes `btlogger [OPTIONS] {out}`; upstream moved it under a `capture` subcommand.
# Passing the wrong one is not a soft failure: the extra word is eaten as the OUTPUT PATH,
# so it writes a file named `capture` and exits. Verified against the installed binary on
# 2026-07-30, when the documented `btlogger capture --format pcapng` did exactly that.
btlogger_argv() {
  if "$PMD3" btlogger --help 2>&1 | grep -qE '^\s+capture\s'; then
    echo "btlogger capture"
  else
    echo "btlogger"
  fi
}

# The real precondition is that HCI frames are FLOWING. A missing Bluetooth logging profile,
# or a locked phone, opens cleanly and records nothing, which is indistinguishable from a
# quiet radio unless you look for frames. Asking the project's own reader means a capture
# that passes here cannot then fail to decode for a container reason.
frames_seen() {
  uv run --project "$REPO_DIR" --no-sync python -c '
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from decode_govee import iter_frames
try:
    print(sum(1 for _ in iter_frames(Path(sys.argv[2]).read_bytes(), allow_truncated=True)))
except Exception:
    print(0)' "$SELF_DIR" "$1" 2>/dev/null || echo 0
}

case "${1:-}" in
  start)
    name="${2:-}"; [ -n "$name" ] || usage 1
    sha="${3:--}"
    [ "$sha" = - ] || [[ "$sha" =~ ^[0-9a-f]{64}$ ]] || { echo "prediction SHA-256 must be 64 lowercase hex" >&2; exit 1; }
    [ -f "$STATE" ] && { read -r old _ < "$STATE"; stop_logger "$old"; rm -f "$STATE"; }
    name="${name//[^A-Za-z0-9._-]/_}"; mkdir -p "$CAP"
    suffix="$(capture_suffix)"
    out="$CAP/$name.$suffix"; rm -f "$out"
    pid="$(start_logger "$out" "$name")"
    model="${GOVEE_MODEL:--}"
    [ "$model" = - ] || [ "$model" = H617A ] || [ "$model" = H6199 ] || {
      stop_logger "$pid"
      echo "GOVEE_MODEL must be H617A or H6199" >&2
      exit 1
    }
    printf '%s %s %s %s %s %s %s\n' \
      "$pid" "$name" "$(date --iso-8601=ns)" "$sha" "${GOVEE_EXPECTED_PEER:--}" "$suffix" "$model" > "$STATE"
    : > "$CAP/$name.actions.tsv"
    for _ in $(seq 1 "$PREFLIGHT_SECONDS"); do
      sleep 1; [ "$(frames_seen "$out")" -gt 0 ] && break
    done
    if [ "$(frames_seen "$out")" -eq 0 ]; then
      stop_logger "$pid"; rm -f "$STATE" "$CAP/$name.actions.tsv"
      echo "capture preflight failed: no HCI frames in ${PREFLIGHT_SECONDS}s. In order:" >&2
      echo "  1. install Apple's Bluetooth Logging profile ($BLUETOOTH_LOGGING_PROFILE_URL;" >&2
      echo "     UUID $BLUETOOTH_LOGGING_PROFILE_UUID), then toggle Bluetooth;" >&2
      echo "  2. backend is '$BACKEND'. On WSL with the phone natively owned it must be" >&2
      echo "     idevicebtlogger; the pymobiledevice3 backend cannot reach that phone and" >&2
      echo "     records an empty capture. resolve_device derives this, so a shell that" >&2
      echo "     never called it is the usual cause." >&2
      echo "  3. toggle Bluetooth off then on. Log: $CAP/$name.log" >&2
      # DO NOT suggest `pymobiledevice3 usbmux list` here. It cannot work on this rig at all:
      # pymobiledevice3 ships a Wsl class whose usbmux address is the Windows iTunes TCP
      # endpoint, so the CLI reports "Failed to connect to usbmuxd socket" while the daemon is
      # running, holds the phone, and answers a hand-written ListDevices perfectly well. That
      # advice cost a session hunting a healthy daemon. USBMUXD_SOCKET_ADDRESS is what makes
      # the library reach the real socket, and devices.env exports it.
      # A LOCKED PHONE IS NOT A CAUSE OF THIS, measured 2026-08-03: with the lock state
      # confirmed LOCKED immediately beforehand, a capture recorded 21 KB in 12s and decoded
      # to 31 ATT frames. Suggesting it first sent a session hunting the wrong thing while a
      # missing logging profile went unread, so it is not listed at all.
      exit 1
    fi
    echo "recording '$name' (pid $pid); mark each action before it starts, then: stop"
    ;;
  mark)
    [ -f "$STATE" ] || { echo "no capture running"; exit 1; }
    shift; label="$*"; [ -n "$label" ] || usage 1
    read -r _ name _ < "$STATE"
    printf '%s\t%s\n' "$(date --iso-8601=ns)" "${label//[$'\t\r\n']/ }" >> "$CAP/$name.actions.tsv"
    echo "marked '$label'"
    ;;
  stop)
    [ -f "$STATE" ] || { echo "no capture running"; exit 1; }
    read -r pid name started sha peer suffix model < "$STATE"
    suffix="${suffix:-pcapng}"
    model="${model:--}"
    decode_model="$model"
    [ "$decode_model" = - ] && decode_model=auto
    out="$CAP/$name.$suffix"
    kill -INT "$pid" 2>/dev/null || true
    for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
    kill "$pid" 2>/dev/null || true
    rm -f "$STATE"
    printf '{"capture":"%s","started_at":"%s","stopped_at":"%s","actions":"%s.actions.tsv","prediction_sha256":%s,"expected_peer":%s,"model":%s}\n' \
      "$name" "$started" "$(date --iso-8601=ns)" "$name" \
      "$([ "${sha:--}" = - ] && echo null || echo "\"$sha\"")" \
      "$([ "${peer:--}" = - ] && echo null || echo "\"$peer\"")" \
      "$([ "$model" = - ] && echo null || echo "\"$model\"")" > "$CAP/$name.meta.json"
    echo "stopped '$name'"
    if [ "${peer:--}" = - ]; then
      # --allow-unattributed, because an unbound session is ad-hoc or direct-mode and a
      # connection that predates the window is its normal state, not a failure. It does NOT
      # weaken the guard that matters here: the decoder still refuses a capture holding more
      # than one BLE connection's worth of Govee traffic, which is a failed run to repeat
      # rather than a result to interpret. That refusal is the whole reason this branch
      # checks an exit status at all. It used to ignore one, and on 2026-08-05 an unbound
      # session holding two live connections stopped clean and was read as one light.
      if ! uv run --project "$REPO_DIR" python "$SELF_DIR/decode_govee.py" "$out" \
        --allow-unattributed --model "$decode_model"; then
        echo "capture '$name' is not usable as evidence about one device" >&2
        echo "  the phone was talking to more than one thing on BLE while this recorded," >&2
        echo "  so no reading off it belongs to any particular device. Narrow it with" >&2
        echo "  'govee-capture.sh decode $name --source <connection> --allow-unattributed'" >&2
        echo "  once you know which connection was the light, or recapture with the others" >&2
        echo "  disconnected." >&2
        exit 3
      fi
    elif ! uv run --project "$REPO_DIR" python "$SELF_DIR/decode_govee.py" "$out" \
      --peer "$peer" --model "$decode_model"; then
      # The decoder already said which peers it did see. This adds the one thing it cannot
      # know: that the session was FOR this device, so a capture without it is a failed run
      # to repeat, not a result to interpret.
      echo "capture '$name' is not usable as evidence about $peer" >&2
      echo "  the app may never have connected, or connected before recording started." >&2
      echo "  Start the capture FIRST, then force a fresh connect, so the HCI connect" >&2
      echo "  event carrying the address lands inside the window." >&2
      # 3, not 1, so down.sh can tell "this capture proves nothing" apart from "there was no
      # capture running", which it has always tolerated and must go on tolerating.
      exit 3
    fi
    ;;
  decode)
    name="${2:-}"; [ -n "$name" ] || usage 1; shift 2
    uv run --project "$REPO_DIR" python "$SELF_DIR/decode_govee.py" "$(capture_path "$name")" "$@"
    ;;
  list)
    shopt -s nullglob
    captures=("$CAP"/*.pcap "$CAP"/*.pcapng)
    [ "${#captures[@]}" -gt 0 ] && ls -lh "${captures[@]}" || echo "no captures yet"
    ;;
  *) usage 0 ;;
esac
