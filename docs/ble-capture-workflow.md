# Decoding the Govee BLE protocol (capture workflow)

How this integration's BLE protocol is decoded: capture the vendor iOS app talking to the
strip over Bluetooth, then read the packets. This is how the H617A per-segment, scene and
DIY commands documented in `ble-protocol-h617a.md` were worked out. The method is fast:
each action is one short capture that is decoded immediately, then cross-checked by driving
the strip directly and reading its state back.

## Idea

The vendor app already knows how to drive every feature. If we watch the app's Bluetooth
traffic while it performs a single action, the bytes it sends are the command we need. We
capture the phone's live HCI stream to a `.pcap`, one action at a time, and decode only the
packets that belong to the strip.

## Environment

- **Windows + WSL.** A prebuilt libimobiledevice `idevicebtlogger` runs on Windows and
  streams the phone's live Bluetooth HCI to a `.pcap`. WSL drives it by shelling into
  Windows PowerShell (`pwsh.exe`), so all commands are run from the WSL shell.
- **An iPhone with Apple's Bluetooth logging profile installed**, paired and trusted to the
  Windows host. Installing that profile and the libimobiledevice toolchain is a one-time,
  environment-specific setup kept outside this repo.
- The project's `uv` environment in WSL for the decoder. No Wireshark required.

## Persistent iPhone control

Autonomous runs should keep one CoreDevice media stream open for one approved, bounded target,
normally one scene or one control family. Opening and closing a stream for every tap is slow and
can wedge `displayservice`, but broad multi-scene sessions accumulate too much state and evidence.

```bash
python -m pymobiledevice3 developer core-device display serve-web \
  --bind 127.0.0.1 --http-port 18080 --no-audio --userspace
```

The loopback viewer exposes ordered `/touch` requests while the authenticated stream remains open.
Keep it bound to `127.0.0.1`; the control endpoints are intentionally unauthenticated. Use one
phone operator to mark, drive, capture and decode the approved target, then stop and reconcile it
before starting another. Do not queue follow-on targets without owner approval. Take only decisive
screenshots, retain their full files locally and return text-only findings to the main session.

After an iPhone restart, remount the Developer Disk Image before using developer services:

```bash
python -m pymobiledevice3 mounter auto-mount --userspace
```

On a later screenshot or touch timeout, stop the persistent viewer, probe
`display get-media-stream-server-status`, mount or remount the Developer Disk Image, and verify
with one screenshot before asking for a phone restart. These recovery steps do not write BLE
state.

## Tools (`tools/ble/`)

- `govee-capture.sh`: start/stop the capture and auto-decode. It starts `idevicebtlogger`
  detached and stops it **by PID**, because the logger has no duration flag and Ctrl+C
  cannot be delivered to a Windows process from WSL. You therefore tap the app at your own
  pace between `start` and `stop`. The `mark` command writes timestamped labels for each action
  in a batched feature-family capture.
- `decode_govee.py`: parse the `.pcap` and print the strip's packets as labelled hex.
- `validate_protocol.py` + `validation_plan.py`: a **guided live validation harness**. It runs a
  comprehensive ordered checklist one action at a time (e.g. "Set brightness to 1%"), watches the
  live sniff, decodes the frame the app emits, and auto-diffs it against what our `protocol.py`
  would send — PASS/FAIL with a byte diff, no AI in the loop. See "Guided live validation" below.

Set `GOVEE_BLE_DIR` (WSL tooling directory), `GOVEE_WIN_CAP` (Windows capture
directory) and `GOVEE_BTLOGGER` (Windows `idevicebtlogger.exe` path) before
using live or replay modes. `PWSH` is optional and defaults to `pwsh.exe`.
The live commands fail before prompting if the logger does not produce a valid
pcap header within five seconds.

## Guided live validation (`validate_protocol.py`)

For bulk protocol accuracy checks, the harness replaces the manual per-file loop with a scripted,
self-checking session:

```bash
# Full live run: starts the sniff, prompts each action, stops the sniff, writes a report.
tools/ble/validate_protocol.py --live
tools/ble/validate_protocol.py --live --only F        # just the music section
# Offline self-test / development against an existing capture:
tools/ble/validate_protocol.py --replay captures/music-all.pcap --only F
```

Each checklist step declares how to recognise its frame and either an exact expected value
(computed from `protocol.py`, so drift shows as FAIL) or a structural validator (decodes and
reports, e.g. music mode code, segment mask, timer fields). Sections: A basics, B colour-temp,
C segments, D scenes, E DIY, F music, G timers, H queries. A markdown + JSON report is written to
the captures dir. The plan is the single place to extend coverage as the protocol grows.

## The loop (one action per file)

```bash
tools/ble/govee-capture.sh start seg-red    # begin capture
#   -> perform exactly ONE action in the Govee app (e.g. set the strip red)
tools/ble/govee-capture.sh stop              # stop + decode
tools/ble/govee-capture.sh decode seg-red --all   # re-decode, incl. non-Govee ATT values
```

Keeping each action in its own named file (`seg-red`, `scene-halloween`, ...) makes the
captures trivial to compare later.

## Batched feature-family loop

Use one capture for a short A/B/A family when stopping for every action would add more hand-off
overhead than evidence. Mark each action immediately before it starts and leave about three
seconds between actions:

```bash
tools/ble/govee-capture.sh start music-style-batch
tools/ble/govee-capture.sh mark "Bloom Dynamic"
# perform the action
tools/ble/govee-capture.sh mark "Bloom Calm"
# perform the action
tools/ble/govee-capture.sh mark "Bloom Dynamic revert"
# perform the action
tools/ble/govee-capture.sh stop
```

The capture writes `<name>.actions.tsv` and references it from `<name>.meta.json`. Prefer the
one-action loop when a control has volatile neighbouring bytes or the action sequence cannot be
made unambiguous.

## How the decoder isolates the strip

The `.pcap` is libpcap link type 201 (`DLT_BLUETOOTH_HCI_H4_WITH_PHDR`). The decoder walks
HCI H4 -> ACL -> L2CAP -> ATT and keeps only the ATT writes (phone -> strip) and
notifications (strip -> phone). Among those it prints the ones that look like this device's
packets: **20 bytes, first byte `0x33` (command), `0xAA` (query/status) or `0xA3`
(multi-frame), and `byte[19] == XOR(byte[0..18])`**. That header-plus-checksum signature
reliably separates the strip from the phone's other Bluetooth activity. Repeats and the
~2 s keep-alive poll are marked so real changes stand out.

## Decoding method (what makes it productive)

1. **Compare against the existing builders.** Run a captured frame through `protocol.py` in
   the repo `uv` env; many of the strip's commands are byte-identical to the current builders,
   which instantly confirms shared behaviour.
2. **Change one variable per capture.** To attribute a byte to a feature, capture two states
   that differ in exactly one thing and diff the decoded payloads. Example: switching a DIY
   effect from Fade1 to Fade2 changed a single body byte, pinning down the effect-index
   field.
3. **Correlate names from the app.** Parameter *names* never appear in the bytes, so for each
   capture record the effect name, the parameter's app-facing label, and its old/new value.
   Effects with several parameters need one isolated capture per parameter.
4. **Validate by driving the strip directly.** Beyond passive capture, build candidate frames
   with `protocol.py` (or by hand), send them to the strip with the vendor app closed, and read
   the result back through the query path (for example `aa a5` for per-segment colour). A
   round-trip that matches what was written confirms the encode and the decode together.

## Privacy

Raw `.pcap` files contain live Bluetooth traffic (potentially from other nearby devices) and
device identifiers, so they are **kept out of the repo**. Only decoded findings and the
tooling are committed.
