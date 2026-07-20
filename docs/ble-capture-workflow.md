# iPhone-driven Govee BLE capture workflow

This is the method for mapping and verifying the Govee BLE protocol: drive the vendor iOS app on a
USB-tethered iPhone, record the phone's Bluetooth HCI stream, and compare the observed packets with
this integration's builders and parsers in `custom_components/ha_govee_led_ble/protocol.py`.

The method is prediction-first and human-paced. Before each app action, record what the integration
is expected to send or receive. Perform one bounded action, decode its BLE window, compare the
result against the prediction, and restore the device baseline.

## Operating principles

1. Test one device and one control target at a time.
2. Predict the relevant TX command and RX status before changing the app.
3. Treat BLE packets, not UI animation, as proof that a change reached the device.
4. Change one variable at a time. Use A/B/A when a field must be attributed by byte difference.
5. Keep one persistent phone-control stream open for the run; do not open a new media stream per
   tap.
6. Restore the device baseline before closing each capture. Return the BLE link to Home Assistant
   only at an explicitly confirmed session hand-back.

## Components

| Component | Purpose |
| --- | --- |
| `idevicebtlogger` | Streams the iPhone Bluetooth HCI log to a pcap file on Windows. |
| `pymobiledevice3` CoreDevice display service | One authenticated, loopback-only phone viewer and touch channel (screenshots plus taps). |
| `tools/ble/govee-capture.sh` | Starts, marks, stops, and decodes a capture from WSL. |
| `tools/ble/decode_govee.py` | Extracts Govee TX writes and RX notifications from the pcap. |
| `custom_components/ha_govee_led_ble/protocol.py` | Supplies the expected packet builders and parsers for predictions. |

## Environment

The laboratory is Windows with WSL:

- `idevicebtlogger` and `pymobiledevice3` run against the USB-connected iPhone on Windows.
- WSL invokes Windows tooling with `pwsh.exe`.
- The iPhone is paired and trusted, with Apple's Bluetooth logging (PacketLogger) profile installed.
- The project uses `uv` for decoding.

Set these before using the capture wrapper:

```bash
export GOVEE_BLE_DIR=/mnt/z/libimobiledevice
export GOVEE_WIN_CAP='Z:\libimobiledevice\captures'
export GOVEE_BTLOGGER='Z:\libimobiledevice\bin\idevicebtlogger.exe'
```

`PWSH` is optional and defaults to `pwsh.exe`. `start` fails within five seconds if the logger does
not write a valid pcap header, which means the phone's HCI stream is not flowing (locked phone,
missing logging profile, or a stalled adapter that a Bluetooth off/on toggle restarts).

## Safety and ownership

- Home Assistant owns the BLE link outside an active live session.
- Disable only the target device's config entry before connecting through Govee Home, and keep it
  disabled between runs in the same session.
- Never restart Home Assistant for a hand-off; enable and reload the single entry instead.
- Keep the designated H617A test strip within the approved brightness limit (10%).
- Never touch another device that merely shares the same model.
- H6199 evidence is app-sniff only. Do not send candidate frames from a development Bluetooth
  adapter.

## Persistent phone control

Start one viewer for the run:

```bash
python -m pymobiledevice3 developer core-device display serve-web \
  --bind 127.0.0.1 --http-port 18080 --no-audio --userspace
```

The touch endpoint is unauthenticated, so it must stay on loopback. From WSL, call the Windows
viewer with `curl.exe`, not WSL `curl`:

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

The endpoint returns before the device necessarily completes the action, so leave about three
seconds before assessing BLE or visual state. A slider needs a `drag` that starts on the handle.
Keep the loop brisk because a provisioned phone can auto-lock and cannot be unlocked by the
automation.

## Capture loop

Record the prediction (expected TX frame or structural signature, and the expected RX status where
the device exposes one) and the exact baseline before starting. Then, one action at a time:

```bash
tools/ble/govee-capture.sh start <name>   # begin recording
tools/ble/govee-capture.sh mark <label>   # timestamp each action immediately before it happens
tools/ble/govee-capture.sh stop           # stop and decode the capture
tools/ble/govee-capture.sh decode <name>  # re-decode an existing capture
tools/ble/govee-capture.sh list           # list captures
```

`stop` is by PID, so actions are taken at your own pace. Compare the decoded frames with the
prediction. A mismatch stays a mismatch; do not edit the prediction after the capture. Restore the
baseline before the next target.

Commit only decoded protocol findings, tests, and documentation. Raw pcaps can contain nearby
Bluetooth traffic and device identifiers, so they stay outside the repository.

## Decoder boundary

The pcap uses `DLT_BLUETOOTH_HCI_H4_WITH_PHDR`. `decode_govee.py` walks HCI H4, ACL, L2CAP, and
ATT, then keeps writes and notifications matching the Govee packet signature:

- 20 bytes;
- first byte `0x33`, `0xAA`, or `0xA3`;
- byte 19 equals the XOR of bytes 0 through 18.

It also tracks LE connection and disconnection events, retaining the HCI connection handle and peer
address on each ATT record so frames can be attributed to the target. Direction matters: TX is the
phone-to-device command path and RX is acknowledgement or status from the device.

## Recovery

Repeated one-shot screenshot or HID commands create new media streams and can wedge
`displayservice`. Prefer the persistent viewer. If it fails:

1. Stop the viewer cleanly.
2. Probe `display get-media-stream-server-status`.
3. Run `pymobiledevice3 mounter auto-mount --userspace` (the phone must be unlocked).
4. If the probe still fails, unmount and remount the Developer Disk Image.
5. Verify recovery with one screenshot.
6. Request an iPhone restart only if the remount sequence fails.

Do not run recovery while a healthy viewer is active.

## Session hand-back

Do not return the target to Home Assistant automatically. After the owner explicitly ends the live
session:

1. Confirm the device baseline in Govee Home, then terminate the app.
2. Enable only the target Home Assistant entry.
3. Reload it with `POST /api/config/config_entries/entry/<entry_id>/reload`.
4. Require `state=loaded`, `disabled_by=null`, and entity availability.
