#!/usr/bin/env bash
# Windows iPhone backend for WSL UI sessions.

WINDOWS_RUN_DIR="$WSL_WINDOWS_TOOL_DIR/runs"
WINDOWS_CAPTURE_DIR="$WINDOWS_TOOL_DIR\\captures"
GOVEE_CAPTURE_DIR="${WINDOWS_GOVEE_CAPTURE_DIR:-$WSL_WINDOWS_TOOL_DIR/captures}"
GOVEE_SHOT_DIR="$GOVEE_CAPTURE_DIR/shots"
mkdir -p "$WINDOWS_RUN_DIR" "$GOVEE_CAPTURE_DIR" "$GOVEE_SHOT_DIR"

windows_phone_action() {
  local action=$1
  export WSLENV="${WSLENV:+$WSLENV:}PHONE_UDID:WDA_RUNNER_BUNDLE_ID"
  pwsh.exe -NoProfile -ExecutionPolicy Bypass \
    -File "$(wslpath -w "$HARNESS_DIR/windows_phone.ps1")" -Action "$action" |
    tr -d '\r'
}

windows_sync_phone_tools() {
  cp "$HARNESS_DIR/ax.py" "$WSL_WINDOWS_TOOL_DIR/ax.py"
  cp "$HARNESS_DIR/wda.py" "$WSL_WINDOWS_TOOL_DIR/wda.py"
  cp "$HARNESS_DIR/wda_daemon.py" "$WSL_WINDOWS_TOOL_DIR/wda_daemon.py"
}

pmd3() {
  timeout "$PMD3_COMMAND_TIMEOUT" "$WINDOWS_PMD3_PYTHON" -m pymobiledevice3 "$@" |
    tr -d '\r'
}

dvt() { pmd3 developer dvt "$@" --userspace; }

pmd3_python() { echo "$WINDOWS_PMD3_PYTHON"; }

ax() {
  windows_sync_phone_tools
  timeout "$PMD3_COMMAND_TIMEOUT" "$WINDOWS_PMD3_PYTHON" \
    "$WINDOWS_TOOL_DIR\\ax.py" "$@" | tr -d '\r'
}

wda() {
  windows_sync_phone_tools
  "$WINDOWS_CLIENT_PYTHON" "$WINDOWS_TOOL_DIR\\wda.py" "$@" | tr -d '\r'
}

wda_serving() {
  local response
  response="$(curl.exe -sf --max-time 3 http://127.0.0.1:8100/status 2>/dev/null | tr -d '\r')" ||
    return 1
  grep -q '"ready"' <<<"$response"
}

wda_up() {
  wda_serving && return 0
  windows_sync_phone_tools
  tunnel_up || return 1
  windows_phone_action start-wda >/dev/null 2>&1 &
  for _ in $(seq 1 180); do
    sleep 1
    wda_serving && return 0
  done
  echo "WDA did not come up; see $WINDOWS_RUN_DIR/wda.err.log" >&2
  return 1
}

wda_down() {
  windows_phone_action stop-wda
  rm -f "$HARNESS_RUN_DIR/wda-session"
}

tunneld_serving() {
  local response
  response="$(curl.exe -sf --max-time 3 http://127.0.0.1:49151 2>/dev/null | tr -d '\r')" ||
    return 1
  grep -q tunnel-address <<<"$response"
}

tunneld_listening() {
  pwsh.exe -NoProfile -Command \
    "if (Get-NetTCPConnection -LocalPort 49151 -State Listen -ErrorAction SilentlyContinue) { 'yes' }" |
    tr -d '\r' | grep -q yes
}

tunnel_up() {
  tunneld_serving && return 0
  windows_phone_action start-tunneld
  for _ in $(seq 1 30); do
    sleep 1
    tunneld_serving && return 0
  done
  echo "Windows tunneld did not serve the phone" >&2
  return 1
}

# Windows tunneld is intentionally persistent. It is loopback-only and avoids a UAC prompt
# on every harness cycle.
tunnel_down() { return 0; }

serve_web_url() { echo "http://127.0.0.1:$SERVE_WEB_PORT"; }

hid_alive() {
  curl.exe -sf --max-time 3 -o NUL "$(serve_web_url)/viewer.js" 2>/dev/null
}

hid_up() {
  hid_alive && return 0
  windows_phone_action start-serve-web >/dev/null 2>&1 &
  for _ in $(seq 1 40); do
    sleep 1
    hid_alive && return 0
  done
  echo "serve-web did not come up; see $WINDOWS_RUN_DIR/serve-web.err.log" >&2
  return 1
}

hid_down() { windows_phone_action stop-serve-web; }

touch_post() {
  curl.exe -s --max-time 15 -o NUL -w '%{http_code}' -X POST \
    -H 'Content-Type: application/json' \
    -d "{\"type\":\"$1\",\"x\":$2,\"y\":$3}" "$(serve_web_url)/touch" |
    tr -d '\r'
}

phone_present() {
  local listing
  listing="$(pmd3 usbmux list 2>/dev/null)" || { echo UNKNOWN; return; }
  case "$listing" in *"$PHONE_UDID"*) echo PRESENT ;; *) echo ABSENT ;; esac
}

require_phone() {
  case "$(phone_present)" in
    PRESENT) return 0 ;;
    ABSENT)
      echo "$PHONE_UDID is not visible to Windows Apple Mobile Device Service." >&2
      echo "Connect and unlock it, then accept any trust prompt." >&2
      return 1
      ;;
    *)
      echo "Windows pymobiledevice3 could not determine whether the phone is connected." >&2
      return 1
      ;;
  esac
}

mount_developer_image() { pmd3 mounter auto-mount; }

shot() {
  local name full_windows full_wsl small_wsl
  name="$(date +%Y%m%d-%H%M%S)-${1:-shot}"
  full_windows="$WINDOWS_CAPTURE_DIR\\shots\\$name.png"
  full_wsl="$GOVEE_SHOT_DIR/$name.png"
  small_wsl="$GOVEE_SHOT_DIR/$name-small.png"
  dvt screenshot "$full_windows" >/dev/null 2>&1
  [ -s "$full_wsl" ] || { echo "screenshot failed; DDI mounted?" >&2; return 1; }
  uv run --no-sync --project "$REPO_DIR" python -c "
from PIL import Image; import sys
i = Image.open(sys.argv[1]); s = float(sys.argv[3])
i.resize((int(i.width * s), int(i.height * s)), Image.LANCZOS).save(sys.argv[2])" \
    "$full_wsl" "$small_wsl" "$SHOT_SCALE"
  echo "$small_wsl"
}

require_bluetooth_transport() {
  [ -x "$WINDOWS_CLIENT_PYTHON" ] || {
    echo "Windows BLE Python is missing at $WINDOWS_CLIENT_PYTHON" >&2
    return 1
  }
  "$WINDOWS_CLIENT_PYTHON" -c "import bleak, kaitaistruct" >/dev/null 2>&1 || {
    echo "Bleak and kaitaistruct 0.11 must be installed in the Windows BLE environment" >&2
    return 1
  }
}

govee_send() {
  mkdir -p "$WSL_WINDOWS_TOOL_DIR/generated_protocol"
  find "$WSL_WINDOWS_TOOL_DIR/generated_protocol" -maxdepth 1 -type f -name '*.py' -delete
  cp "$REPO_DIR/custom_components/ha_govee_led_ble/generated_protocol/"*.py \
    "$WSL_WINDOWS_TOOL_DIR/generated_protocol/"
  cp "$REPO_DIR/tools/ble/generated_protocol_view.py" "$WSL_WINDOWS_TOOL_DIR/generated_protocol_view.py"
  cp "$REPO_DIR/tools/ble/govee_send.py" "$WSL_WINDOWS_TOOL_DIR/govee_send.py"
  "$WINDOWS_CLIENT_PYTHON" "$WINDOWS_TOOL_DIR\\govee_send.py" "$@" |
    tr -d '\r'
}

capture() {
  echo "Windows pymobiledevice3 capture is unsupported; use up.sh app so WSL owns the phone." >&2
  return 1
}
