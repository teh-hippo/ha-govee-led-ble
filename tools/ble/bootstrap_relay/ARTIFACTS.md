# Run A file and process inventory

## Branch files

- `govee_relay/`: relay, TLS, HTTP, upstream, redaction, event and observer source.
- `tests/`: fabricated loopback-only tests.
- `THREAT-MODEL.md`: trust boundaries, controls and residual risk.
- `RUN-A.md`: unchanged-relay procedure and restore path.
- `RUN-B.md`: bounded mqttAddress mutation and execution result.
- `RUN-C.md`: controlled TCP/8883 ClientHello result.
- `RUN-D.md`: controlled server-handshake negative result.
- `PAUSE-GATE.md`: evidence required before live approval.
- `REQUEST-FINGERPRINT.md`: proven and missing request-shape facts.
- `baseline.sh`: guarded calibration/version baseline and marker.
- `run-a.sh`: local coordinator and direct-device acknowledgement gate.
- `ai-lab.sh`: Proxmox/AI-lab deployment and relay listener lifecycle.
- `windows-ble.sh`: Windows BLE preflight, version query and provisioning dispatch.
- `ha-platform.sh`: HA-platform-only ownership hand-off.
- `rehearse-infra.sh`: device-free live infrastructure rehearsal.
- `govee_relay/live.py`: guarded live relay CLI.
- `govee_relay/mutation.py`: byte-surgical root mqttAddress replacement.
- `govee_relay/mqtt_probe.py`: bounded ClientHello and MQTT CONNECT-shape probes.
- `govee_relay/unifi.py`: reversible UniFi lifecycle.
- `evidence/`: selected redacted live events and semantic version canaries.

Runtime directories are `0700`; runtime state, event, certificate and key files are `0600`.
Committed redacted evidence uses normal repository permissions.

## Run A processes

- relay process;
- structured-event writer inside relay;
- non-forwarding DNS observer;
- guarded Windows BLE provisioning process;
- local Home Assistant platform hand-back trap.

No MQTT broker, proxy daemon, pcap TLS key logger or general-purpose DNS forwarder exists.

## Run A transient files

- short-lived RSA certificate and key;
- structured redacted event log;
- unapplied/applied isolation manifest state;
- no raw request or response file;
- no credential file;
- no keylog or core dump.

The passphrases exist only in the coordinating shell's memory and stdin pipes. The BLE frame
writer's credential-bearing `WRITE` lines are filtered before any persistent log.

The retained Run A evidence is `evidence/events-run-a-20260808-2350.jsonl` plus semantic
version canaries. Transient remote run directories and keys were deleted after restore.

Run B evidence is `evidence/events-run-b-20260808-2355.jsonl`; it records one upstream fetch,
one mutation, one relay, one nonce DNS match and an immediate DNS-triggered stop.

Run C and D evidence is migrated under `evidence/` on the research branch. Only redacted
structured events and semantic version canaries are retained.

## Reproduce validation

From this directory:

```bash
bash run-tests.sh -vv
uv run --project ~/ha-govee-led-ble --no-sync ruff check .
uv run --project ~/ha-govee-led-ble --no-sync ruff format --check .
uv run --project ~/ha-govee-led-ble --no-sync mypy \
  --cache-dir=/dev/null govee_relay tests
PYTHONPATH=. uv run --project ~/ha-govee-led-ble --no-sync \
  python -m govee_relay.prepare --output evidence/prepared.json
```

The isolated test runner disables third-party pytest plugins and Python bytecode output.
