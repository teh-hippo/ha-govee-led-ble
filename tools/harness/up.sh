#!/usr/bin/env bash
# up.sh {app|ui|direct} [device] -- take the device's BLE link and stand the harness up.
#
#   app     the phone drives and we sniff: gesture session + Govee app + HCI capture
#   ui      the phone drives without capture: gesture session + WDA + Govee app
#   direct  we drive over BLE with govee_send.py: no phone involved at all
#
# Set HARNESS_PREDICTION_SHA to the SHA-256 of the probe's registered prediction and it is
# recorded in the capture's meta.json. A session capture is where a prediction has to be
# bound, because the capture IS the evidence the prediction is judged against; without this
# every app-mode probe silently records prediction_sha256: null.
#
# Both release the Home Assistant entry first, because a Govee device has one BLE link and
# HA holds it by default. Direct mode touches no phone service, so it runs headless.
set -euo pipefail

mode="${1:?app|ui|direct required}"
case "$mode" in app|ui|direct) ;; *) echo "mode must be app, ui or direct" >&2; exit 2 ;; esac

# Windows pymobiledevice3 produces an empty Bluetooth capture. App mode moves the phone to
# WSL before phone.sh selects a backend. Its userspace RSD path keeps WDA and HID with the
# native usbmuxd owner instead of asking a native tunneld to rediscover the phone.
if [ "$mode" = app ] &&
   { [ "${HARNESS_HOST_KIND:-}" = wsl ] ||
     { [ -z "${HARNESS_HOST_KIND:-}" ] && grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; }; }; then
  export HARNESS_PHONE_BACKEND=native
  export HARNESS_RSD_BACKEND=userspace
fi

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/phone.sh"
resolve_device "${2:-$DEVICE_DEFAULT}"

phone_usbipd_acquired=0
cleanup_phone_ownership() {
  [ "$phone_usbipd_acquired" = 1 ] || return
  phone_usbipd_release || echo "WARNING: iPhone USB ownership teardown failed" >&2
}

# Phone-side setup runs BEFORE Home Assistant is touched, so a failure here leaves the entry
# enabled. App mode installs its ownership rollback as soon as the phone reaches WSL.
if [ "$mode" != direct ]; then
  if [ "$mode" = app ]; then
    # The trap is installed BEFORE the acquire, not after it. Acquire records ownership
    # state partway through so a half-finished attach is still rolled back, but under
    # `set -e` a failure there exits immediately: installing the trap afterwards meant the
    # one path that most needs the rollback was the one path that never armed it.
    phone_usbipd_acquired=1
    trap cleanup_phone_ownership EXIT
    phone_usbipd_acquire
  fi
  # First, because everything below it depends on the phone being reachable and each of
  # them reports its absence as a failure of something else.
  require_phone || exit 1
  # Mounted over plain lockdown BEFORE any tunnel, because the mounter needs no tunnel and
  # is the only cold-start reading of the lock state. Its LOCKED verdict is what a locked
  # phone actually looks like here; the screenshot below cannot answer until this succeeds.
  require_developer_image || exit 1
  if [ "$HARNESS_RSD_BACKEND" != userspace ]; then
    tunnel_up
  fi
  # The one state that fails SILENTLY: a locked phone serves screenshots and capture while
  # backboardd drops every gesture. Everything else here fails loudly on its own.
  require_unlocked || exit 1
  hid_up
else
  [ -n "$DEVICE_ADDRESS" ] || { echo "$DEVICE_NAME has no address; direct mode is H617A only" >&2; exit 1; }
  require_bluetooth_transport || exit 1
fi

echo "== releasing BLE from Home Assistant ($DEVICE_NAME / $DEVICE_SKU)"
ha_entry "$DEVICE_ENTRY" disable | grep -qi '"success": true' || { echo "HA did not release" >&2; exit 1; }

# From here the device has NO owner. A trap rather than a handler per exit, so a step added
# later cannot forget to give the link back, and serve-web (unauthenticated full control of
# the phone) never outlives a failed stand-up. The capture goes too: HARNESS_STATE_FILE is
# only written on success, so a later down.sh would default to direct mode and never stop
# it, leaving a stale .current that act.sh would mark against a file nothing is writing.
harness_is_up=0
cleanup_failed_standup() {
  [ "$harness_is_up" = 1 ] && return
  if [ "$mode" != direct ]; then
    dvt pkill "$GOVEE_APP_PROCESS" >/dev/null 2>&1 || true
    wda_down || echo "WARNING: WDA teardown failed during stand-up cleanup" >&2
    hid_down || echo "WARNING: serve-web teardown failed during stand-up cleanup" >&2
    if [ "$HARNESS_RSD_BACKEND" != userspace ]; then
      tunnel_down || echo "WARNING: tunneld teardown failed during stand-up cleanup" >&2
    fi
    capture stop >/dev/null 2>&1 || true
    phone_usbipd_release || echo "WARNING: iPhone USB ownership teardown failed" >&2
  fi
  ha_entry "$DEVICE_ENTRY" enable >/dev/null 2>&1 || {
    echo "COULD NOT RETURN BLE TO HOME ASSISTANT - run tools/harness/down.sh" >&2
    return 1
  }
}
trap cleanup_failed_standup EXIT

if [ "$mode" = app ]; then
  # The runner must be ready before capture starts, but it does not launch Govee. That lets
  # the first WDA session activate the app immediately after the logger is recording.
  wda_up
  # The preflight capture IS the session capture. govee-capture.sh refuses to start unless
  # the decoder reads frames out of it, which is the check that catches a missing Bluetooth
  # logging profile or a dead HCI stream; do not add a second, weaker copy here.
  session_capture="session-$DEVICE_NAME-$(date +%Y%m%d-%H%M%S)"
  # Bind the capture to the device it is a capture OF. Without this a session in which the
  # app never reached the light decodes cleanly and empty, which reads as a quiet device.
  [ -n "$DEVICE_EXPECTED_PEER" ] || {
    echo "$DEVICE_NAME has neither a connect nor a sniff address" >&2
    echo "add it to DEVICE_SNIFF_ADDRESS in the identity file so its capture can be attributed" >&2
    exit 1
  }
  capture_start_log="$HARNESS_RUN_DIR/capture-start.log"
  GOVEE_EXPECTED_PEER="$DEVICE_EXPECTED_PEER" GOVEE_MODEL="$DEVICE_SKU" \
    capture start "$session_capture" "${HARNESS_PREDICTION_SHA:--}" \
    >"$capture_start_log" 2>&1 &
  capture_start_pid=$!
  sleep 1
  wda_activate_govee
  if ! wait "$capture_start_pid"; then
    cat "$capture_start_log" >&2
    exit 1
  fi
  echo "== up: capture '$session_capture', WDA ready, gestures at $(serve_web_url)"
elif [ "$mode" = ui ]; then
  wda_up
  wda_activate_govee
  echo "== up: WDA ready, gestures at $(serve_web_url)"
else
  ble_link_is_free "$DEVICE_ADDRESS" || { echo "no read-back from $DEVICE_ADDRESS; something holds the link" >&2; exit 1; }
  echo "== up: host owns the link to $DEVICE_ADDRESS ($DEVICE_SKU)"
fi

printf '%s %s %s %s %s\n' \
  "$mode" "$DEVICE_NAME" "$DEVICE_ENTRY" "$HARNESS_PHONE_BACKEND" "$HARNESS_RSD_BACKEND" > "$HARNESS_STATE_FILE"
harness_is_up=1
[ "$mode" != direct ] && shot "up-$DEVICE_NAME"
exit 0
