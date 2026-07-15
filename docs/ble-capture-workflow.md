# iPhone-driven Govee BLE capture workflow

This workflow maps and verifies the Govee BLE protocol by driving the vendor iOS app, recording
the phone's Bluetooth HCI stream, and comparing the observed packets with this integration's
builders and parsers.

The method is prediction-first. Before each app action, record what the integration is expected to
send or receive. Perform one bounded action, decode its BLE window, compare the result, restore the
device, and return its BLE link to Home Assistant.

## Operating principles

1. Test one named device and one control target at a time.
2. Predict the relevant TX command and RX acknowledgement or status before changing the app.
3. Treat BLE packets, not UI animation, as proof that a change reached the device.
4. Change one variable at a time. Use A/B/A when a field must be attributed by byte difference.
5. Keep one persistent phone-control stream open for the bounded run. Do not create a new media
   stream for every tap.
6. Take only decisive screenshots. Keep full images locally and return text findings to the main
   investigation.
7. Restore the exact baseline and Home Assistant ownership before closing the run.
8. Stop and reconcile the evidence before starting another target.

## Components

| Component | Purpose |
| --- | --- |
| `idevicebtlogger` | Streams the iPhone Bluetooth HCI log to a pcap file on Windows. |
| `tools/ble/govee-capture.sh` | Starts, marks, stops, and decodes a capture from WSL. |
| `pymobiledevice3` CoreDevice display service | Keeps one authenticated, loopback-only phone viewer and touch channel open. |
| `tools/ble/decode_govee.py` | Extracts Govee TX writes and RX notifications from the pcap. |
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

- Home Assistant owns each BLE link outside an approved capture window.
- Disable only the target device's config entry before connecting through Govee Home.
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
- target model, firmware, app build, and integration commit;
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
4. Home Assistant reports the target entry loaded before hand-off.
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

## Bounded run

### 1. Hand the link to the app

Disable only the target Home Assistant config entry. Open Govee Home, select the target, and
confirm the app has connected before starting the evidence window.

### 2. Start and mark the capture

```bash
tools/ble/govee-capture.sh start 20260715190000-h617a-power-on
tools/ble/govee-capture.sh mark "baseline confirmed"
```

For each action, write the marker immediately before the phone command:

```bash
tools/ble/govee-capture.sh mark "tap power on"
# issue the approved touch
```

Use one capture for a short A/B/A sequence only when every transition is attributable:

```bash
tools/ble/govee-capture.sh mark "set A"
# action A
tools/ble/govee-capture.sh mark "set B"
# action B
tools/ble/govee-capture.sh mark "restore A"
# action A
```

The sidecar `<run>.actions.tsv` stores timestamped labels and `<run>.meta.json` records capture
times. Do not trim trailing zeroes from packet bodies while attributing fields because payload
zeroes and transport padding can be indistinguishable.

### 3. Decode and compare

```bash
tools/ble/govee-capture.sh stop
tools/ble/govee-capture.sh decode 20260715190000-h617a-power-on
```

Compare the observed app TX frame with the prediction from `protocol.py`. Compare the RX reply with
the parser and expected device state. Record exact bytes and any differing payload offsets.

Apply behaviour is determined from the capture:

- A fresh TX `0x33` command or complete `0xA3` transaction means the edit reached the BLE
  transport. Do not tap Apply speculatively.
- Queries, keep-alives, or no new TX command mean the edit did not reach the device. If the UI
  presents Apply, tap it once in a newly marked window.
- TX without the expected RX acknowledgement or status is ambiguous. Query the relevant state and
  record the result rather than assuming success.
- An unexpected command family is a failed prediction. Preserve it and stop before broadening the
  run.

### 4. Restore and return ownership

Restore the exact baseline through the same proven path and confirm it from BLE read-back when
available. Back out of the device page normally, terminate Govee Home, enable the Home Assistant
entry, and `POST /api/config/config_entries/entry/<entry_id>/reload`.

The hand-back is complete only when the entry is loaded and its entities are available. A
`setup_retry` state with an unreachable reason usually means the app still owns the device link.
Do not restart Home Assistant to mask an incomplete hand-off.

### 5. Persist the evidence

For each run, retain:

- the raw pcap and action sidecar outside the repository;
- the prediction and exact observed TX and RX bytes;
- app labels and values needed to interpret each transition;
- the restoration result;
- the model, firmware, app build, and integration commit;
- a concise terminal classification such as validated, mismatch, no BLE action, or unresolved.

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

## Guided validation harness

`validation_plan.py` is the declarative checklist. Each step identifies the relevant frame and
either computes an exact expected packet from `protocol.py` or applies a structural validator.

```bash
tools/ble/validate_protocol.py --live
tools/ble/validate_protocol.py --live --only F
tools/ble/validate_protocol.py --replay captures/music-all.pcap --only F
tools/ble/validate_protocol.py --sim
```

`--sim` proves internal encode, decode, and plan consistency only. It does not validate the
protocol against the app or a device. Live verification remains prediction, app action, observed
BLE, read-back, and restoration.

## Decoder boundary

The pcap uses `DLT_BLUETOOTH_HCI_H4_WITH_PHDR`. The decoder walks HCI H4, ACL, L2CAP, and ATT, then
keeps writes and notifications matching the Govee packet signature:

- 20 bytes;
- first byte `0x33`, `0xAA`, or `0xA3`;
- byte 19 equals the XOR of bytes 0 through 18.

This separates Govee frames from unrelated phone traffic. Direction still matters: TX is the
phone-to-device command path and RX is acknowledgement or status from the device.
