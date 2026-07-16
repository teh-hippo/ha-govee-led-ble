# iPhone-driven Govee BLE capture workflow

This workflow maps and verifies the Govee BLE protocol by driving the vendor iOS app, recording
the phone's Bluetooth HCI stream, and comparing the observed packets with this integration's
builders and parsers.

The method is prediction-first. Before each app action, record what the integration is expected to
send or receive. Perform one bounded action, decode its BLE window, compare the result, and restore
the device baseline. Return its BLE link to Home Assistant only at an explicitly confirmed session
hand-back.

## Operating principles

1. Test one named device and one control target at a time.
2. Predict the relevant TX command and RX acknowledgement or status before changing the app.
3. Treat BLE packets, not UI animation, as proof that a change reached the device.
4. Change one variable at a time. Use A/B/A when a field must be attributed by byte difference.
5. Keep one persistent phone-control stream open for the bounded run. Do not create a new media
   stream for every tap.
6. Take only decisive screenshots. Keep full images locally and return text findings to the main
   investigation.
7. Restore the exact device baseline before closing each run. Retain Govee-session ownership until
   the owner explicitly ends the live session and confirms Home Assistant hand-back.
8. Stop and reconcile the evidence before starting another target.

## Components

| Component | Purpose |
| --- | --- |
| `idevicebtlogger` | Streams the iPhone Bluetooth HCI log to a pcap file on Windows. |
| `tools/ble/govee-capture.sh` | Starts, marks, stops, and decodes a capture from WSL. |
| `pymobiledevice3` CoreDevice display service | Keeps one authenticated, loopback-only phone viewer and touch channel open. |
| `tools/ble/decode_govee.py` | Extracts Govee TX writes and RX notifications from the pcap. |
| `tools/ble/safe_verify.py` | Freezes one private run manifest, records bounded markers, verifies attribution and restoration, and writes terminal evidence. |
| `custom_components/ha_govee_led_ble/protocol.py` | Supplies the expected packet builders and parsers. |
| `tools/ble/validate_protocol.py` | Runs the declarative validation plan against live, replayed, or simulated frames. |

## Environment

The current laboratory uses Windows with WSL:

- `idevicebtlogger` and `pymobiledevice3` run against the USB-connected iPhone on Windows.
- WSL invokes Windows tooling with `pwsh.exe`.
- The iPhone is paired and trusted, with Apple's Bluetooth logging profile installed.
- The project uses `uv` for decoding and validation.

Set these variables before using the capture wrapper:

```bash
export GOVEE_BLE_DIR=/mnt/z/libimobiledevice
export GOVEE_WIN_CAP='Z:\libimobiledevice\captures'
export GOVEE_BTLOGGER='Z:\libimobiledevice\bin\idevicebtlogger.exe'
```

`PWSH` is optional and defaults to `pwsh.exe`. Live capture fails before an action begins if the
logger does not write a valid pcap header within five seconds.

## Safety and ownership

- Home Assistant owns the BLE link before an approved live session begins and after the owner
  explicitly confirms session hand-back.
- Disable only the target device's config entry before connecting through Govee Home.
- Keep that entry disabled between individual runs in the same live session.
- Never restart Home Assistant as part of a hand-off. Enable and reload the single entry instead.
- Keep the designated H617A test strip within the approved brightness limit, currently 10%.
- Never touch another device that merely shares the same model.
- H6199 evidence is app-sniff only. Do not send candidate frames from a development Bluetooth
  adapter. Obtain fresh owner approval before any H6199 action that changes device state.
- Do not begin if the phone is locked, the baseline is unknown, another capture is active, or the
  restoration path is unproven.

## Preflight

Record the following before releasing the BLE link:

- run ID using `<YYYYMMddHHmmss>-<taskid>-<focus>`;
- target model, firmware, app build, integration commit, and frozen catalogue SHA-256;
- exact baseline state, including power, brightness, mode, and relevant parameters;
- one app action to perform;
- expected TX frame or structural signature;
- expected RX acknowledgement or status, where the device exposes one;
- restoration action and read-back;
- config entry that will be disabled and reloaded.

Then confirm:

1. The phone is connected and unlocked.
2. CoreDevice developer services respond.
3. No capture state file or stale logger is active.
4. For the first run, Home Assistant reports the target entry loaded before hand-off. For later
   runs, it remains `not_loaded` with `disabled_by=user`.
5. The app can identify the intended device unambiguously.

## Persistent phone control

Start one viewer for the approved run:

```bash
python -m pymobiledevice3 developer core-device display serve-web \
  --bind 127.0.0.1 --http-port 18080 --no-audio --userspace
```

The touch endpoint is unauthenticated, so it must remain on loopback. When the viewer runs on
Windows, WSL must call it with `curl.exe`, not WSL `curl`:

```bash
curl.exe -fsS \
  -H "Content-Type: application/json" \
  -d '{"type":"tap","x":31059,"y":13278}' \
  http://127.0.0.1:18080/touch
```

Touch coordinates are normalised to `0..65535` independently on each axis:

```text
x = round(pixel_x * 65535 / screenshot_width)
y = round(pixel_y * 65535 / screenshot_height)
```

The touch endpoint returns before the device necessarily completes the action. Leave about three
seconds before assessing BLE or visual state. Keep the loop brisk because a provisioned phone can
auto-lock and cannot be unlocked by the automation.

## Approved bounded verification run

`safe_verify.py` is the required runner for the autonomous verification campaign. Its manifest is
private and uncommitted because it contains the target Bluetooth address, local name, config entry,
entity ID, UI path, control values, and touch coordinates. It also freezes:

- the integration commit, Govee app build, device firmware, and catalogue SHA-256;
- the exact TX and optional RX frames for every window;
- Sunrise and brightness 5% restoration packets;
- the 10% brightness limit, 90-second run limit, and 60-second activity limit.

Every manifest declares its ownership boundary:

```json
{
  "ownership": {
    "start": "home_assistant",
    "end": "govee_home"
  }
}
```

The first run starts with `home_assistant`. Later runs start with `govee_home`. Individual runs end
with `govee_home` unless the owner has explicitly ended the session and confirmed hand-back.

### 1. Freeze the manifest

```bash
RUN_ID=20260715190000-h617a-verify-power
RUN_DIR="$GOVEE_BLE_DIR/runs/$RUN_ID"
MANIFEST="$GOVEE_BLE_DIR/manifests/$RUN_ID.json"

uv run python tools/ble/safe_verify.py init "$MANIFEST" "$RUN_DIR"
PREDICTION_SHA256="$(jq -r .prediction_sha256 "$RUN_DIR/state.json")"
```

Initialisation writes mode-`0600` copies of `manifest.json`, `prediction.json`, and `state.json`.
Every later command rechecks both frozen hashes.

### 2. Start the attributed capture

Start the logger before Govee Home connects so the pcap contains the LE connection event that maps
the target address to its HCI connection handle:

```bash
tools/ble/govee-capture.sh start "$RUN_ID" "$PREDICTION_SHA256"
```

The active capture state carries the same prediction hash. A safe run refuses a legacy capture
started without that hash.

### 3. Record or retain session ownership

For the first run, write a Home Assistant snapshot with this exact shape:

```json
{
  "config_entry_id": "<target entry>",
  "entity_id": "light.cupboard_skirt",
  "entry_state": "loaded",
  "disabled_by": null,
  "entity_available": true,
  "power": "on",
  "brightness_percent": 5,
  "mode": "scene",
  "effect": "Sunrise"
}
```

Record it before disabling the target entry:

```bash
uv run python tools/ble/safe_verify.py ownership "$RUN_DIR" before "$RUN_DIR/ha-before.json"
```

Disable only the target config entry. Open Govee Home, select the target, and confirm its private
identity and connected state. Record a hand-off snapshot proving the entry is `not_loaded` with
`disabled_by` set to `user`:

```json
{
  "config_entry_id": "<target entry>",
  "entity_id": "light.cupboard_skirt",
  "entry_state": "not_loaded",
  "disabled_by": "user"
}
```

```bash
uv run python tools/ble/safe_verify.py ownership "$RUN_DIR" handoff "$RUN_DIR/ha-handoff.json"
```

Then arm the run:

```bash
uv run python tools/ble/safe_verify.py mark "$RUN_DIR" armed \
  --pcap "$GOVEE_BLE_DIR/captures/$RUN_ID.pcap" \
  --viewer-healthy --phone-unlocked --target-confirmed
```

Arming fails unless exactly one active connection handle maps to the frozen target address and no
other or unattributed Govee traffic has appeared.

For subsequent runs, keep the entry disabled, start the new capture, reconnect the target in Govee
Home, confirm the exact baseline, and record:

```json
{
  "config_entry_id": "<target entry>",
  "entity_id": "light.cupboard_skirt",
  "entry_state": "not_loaded",
  "disabled_by": "user",
  "app_connected": true,
  "power": "on",
  "brightness_percent": 5,
  "mode": "scene",
  "effect": "sunrise"
}
```

```bash
uv run python tools/ble/safe_verify.py ownership \
  "$RUN_DIR" retained-before "$RUN_DIR/retained-before.json"
```

### 4. Execute each manifest window

Record the displayed value immediately before Terra performs the approved touch:

```bash
uv run python tools/ble/safe_verify.py mark "$RUN_DIR" power-off:before-action \
  --viewer-healthy --phone-unlocked --displayed "On"
# Terra performs the frozen touch.
uv run python tools/ble/safe_verify.py mark "$RUN_DIR" power-off:after-action \
  --viewer-healthy --phone-unlocked --displayed "Off" --visual confirmed
# Wait for the manifest's settle interval.
uv run python tools/ble/safe_verify.py mark "$RUN_DIR" power-off:settled \
  --viewer-healthy --phone-unlocked
```

Repeat that exact marker sequence for each action and restoration window. The runner writes the
same timestamps to `state.json` and `<run>.actions.tsv`; do not call `govee-capture.sh mark` during
a safe run.

The run invalidates immediately on an out-of-order marker, phone lock, unhealthy viewer, ambiguous
displayed value, action timeout, settle-window write, activity gap above 60 seconds, or total
duration above 90 seconds.

Each `before-action` marker drains and rechecks the attributed capture before Terra may touch the
phone. Each `settled` marker verifies the closed window before the runner accepts another action.

### 5. Retain session ownership and analyse

After the final restoration window, and before stopping or disconnecting the app, record the same
baseline as `retained-after`:

```bash
uv run python tools/ble/safe_verify.py ownership \
  "$RUN_DIR" retained-after "$RUN_DIR/retained-after.json"
```

Then stop and analyse:

```bash
tools/ble/govee-capture.sh stop
uv run python tools/ble/safe_verify.py analyse "$RUN_DIR"
```

After evidence is written, terminate Govee Home cleanly so the next capture can observe a fresh LE
connection event. Leave the Home Assistant entry disabled. This preserves session ownership
without keeping an un-attributable BLE connection across captures.

Analysis rejects missing, duplicate, unexpected, delayed, cross-device, or unattributed Govee
frames. It also rejects any recognised brightness command or status above 10%. It writes
mode-`0600` `evidence.json` and `evidence.md` containing:

- hashes and paths for the pcap, action sidecar, capture metadata, manifest, and prediction;
- all decoded Govee frames and marker records;
- target address and connection handle;
- provenance and ownership snapshots;
- exact restoration evidence;
- a wire-pass, TX-only pass, mismatch, no-write, or invalid verdict.

Commit only decoded protocol findings, tests, and documentation. Raw pcaps can contain nearby
Bluetooth traffic and device identifiers.

## Recovery

Repeated one-shot screenshot or HID commands create new media streams and can wedge
`displayservice`. Prefer the persistent viewer. If it fails:

1. Stop the viewer cleanly.
2. Probe `display get-media-stream-server-status`.
3. Run `pymobiledevice3 mounter auto-mount --userspace`.
4. If the probe still fails, unmount and remount the Developer Disk Image.
5. Verify recovery with one screenshot.
6. Request an iPhone restart only if the remount sequence fails.

Do not run recovery while a healthy viewer is active.

For an invalid safe run, stop the capture and restore Sunrise at 5% through Govee Home. Keep the
Home Assistant entry disabled, then record the retained snapshot:

```bash
uv run python tools/ble/safe_verify.py recover "$RUN_DIR" "$RUN_DIR/retained-recovery.json"
```

Recovery writes terminal `invalid` evidence. The original run can never resume; create a new run
ID after approval.

## Explicit session hand-back

Do not return the target to Home Assistant automatically. After the owner explicitly ends the live
session and confirms hand-back:

1. Confirm Sunrise, on, and 5%.
2. Back out normally and terminate Govee Home.
3. Enable only the target Home Assistant entry.
4. Reload it with `POST /api/config/config_entries/entry/<entry_id>/reload`.
5. Require `state=loaded`, `disabled_by=null`, entity availability, Sunrise, and brightness
   `13/255`.

A final approved run may declare `"end": "home_assistant"` and record the normal `after` snapshot.
If hand-back occurs between runs, retain a separate session hand-back record beside the run
artifacts.

## Guided validation harness

`validation_plan.py` is the legacy declarative checklist. Each step identifies the relevant frame and
either computes an exact expected packet from `protocol.py` or applies a structural validator.

```bash
tools/ble/validate_protocol.py --live
tools/ble/validate_protocol.py --live --only F
tools/ble/validate_protocol.py --replay captures/music-all.pcap --only F
tools/ble/validate_protocol.py --sim
```

`--sim` proves internal encode, decode, and plan consistency only. It does not validate the
protocol against the app or a device. Live verification remains prediction, app action, observed
BLE, read-back, and restoration. Do not use its current live plan for the autonomous campaign
because it contains long sessions and brightness steps above the approved limit.

## Decoder boundary

The pcap uses `DLT_BLUETOOTH_HCI_H4_WITH_PHDR`. The decoder walks HCI H4, ACL, L2CAP, and ATT, then
keeps writes and notifications matching the Govee packet signature:

- 20 bytes;
- first byte `0x33`, `0xAA`, or `0xA3`;
- byte 19 equals the XOR of bytes 0 through 18.

The decoder also tracks LE connection and disconnection events, retaining the 12-bit HCI
connection handle and peer Bluetooth address on each ATT record. The safe runner rejects a frame
that cannot be attributed to the one frozen target connection. Direction still matters: TX is the
phone-to-device command path and RX is acknowledgement or status from the device.
