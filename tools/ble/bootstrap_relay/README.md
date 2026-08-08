# H6199 bootstrap relay tooling

Research tooling for bounded H6199 bootstrap and MQTT endpoint experiments.

The tooling is committed only on the `research/h6199-bootstrap-relay` branch. Tests remain
loopback-only and fabricated. Live-host preflight separately performs a verified TLS prewarm
to Govee without sending HTTP, and infrastructure rehearsal creates then removes disposable
UniFi resources without touching the H6199.

## Run offline tests

```bash
bash run-tests.sh
```

The runner disables third-party pytest plugin autoloading. An autouse fixture rejects every
non-loopback DNS result and socket connection.

## Generate the unapplied evidence manifest

```bash
uv run --project ~/ha-govee-led-ble --no-sync \
  python -m govee_relay.prepare \
  --output evidence/prepared.json
```

Run from this directory, or set `PYTHONPATH` to it. The output contains fabricated request
bytes, runtime versions and the unapplied isolation manifest. It contains no live credential
or device value.

## Current boundary

- Device-facing TLS and HTTP parsing are implemented and tested.
- A raw, verified, one-shot upstream client is implemented and tested against loopback TLS.
- Responses are cached once per run and replayed to retries.
- Response payload bytes are relayed with regenerated HTTP framing.
- JSON schema extraction records paths, types and lengths but not values.
- Dynamic JSON object keys are replaced by placeholders before events are written.
- DNS and NTP listeners are implemented.
- A guarded live launcher, reversible UniFi lifecycle and Home Assistant hand-off are
  implemented.
- The exact UniFi lifecycle, AI-lab swap gate and local DNS/NTP/TLS listeners have been
  rehearsed live and torn down.
- Direct BLE uses the Windows controller with explicit write-without-response semantics;
  AI-lab has no attached Bluetooth adapter.
- Run A completed on 8 August 2026 with one production HTTP 200 response relayed unchanged.
- The 3,347-byte JSON response contained MQTT and certificate material; only redacted schema
  facts were retained.
- The H6199 immediately emitted attributable next-stage DNS after the relay.
- Restore association and HA ownership were confirmed, then both temporary WLANs, the VLAN,
  firewall policies, relay listeners, transient keys and swap override were removed.
- Run B completed with only the root `mqttAddress` JSON string token changed to a per-run
  nonce. The H6199 queried that nonce, received NXDOMAIN and the relay stopped immediately.
- Run C proved endpoint and port control through a matching-SNI TLS ClientHello on AI-lab.
- Run D proved the device closes during the self-signed server handshake; the exact rejection
  cause remains unresolved.
- No client certificate, MQTT CONNECT or CONNACK was exchanged.

Committed evidence contains only redacted structured events and semantic version canaries.
Transient certificates, private keys, Wi-Fi credentials and raw production payloads are not
stored in Git.
