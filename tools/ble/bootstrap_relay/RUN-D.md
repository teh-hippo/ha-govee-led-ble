# Run D: controlled MQTT TLS handshake

Run D reached its bounded negative result on 9 August 2026.

## Boundaries

- Repeat the Run C endpoint and port mutation.
- Present a fresh RSA certificate for the nonce hostname.
- Use TLS 1.2 and the proven `AES256-SHA256` cipher profile.
- Do not request a client certificate.
- If TLS succeeds, retain only MQTT CONNECT structure and close before CONNACK.

## Result

- Production returned HTTP 200 and the single `mqttAddress` token was changed.
- The H6199 resolved the nonce and opened the controlled endpoint.
- During the server-side TLS handshake, the peer closed and OpenSSL reported
  `UNEXPECTED_EOF_WHILE_READING`.
- The evidence proves the device rejected or abandoned the server flight, but does not prove
  whether the cause was certificate trust, certificate shape or another handshake property.
- No TLS session, client certificate, MQTT CONNECT or CONNACK occurred.
- The first unsuccessful attempt used the older deadline-only diagnostics; the final attempt
  stopped on the first redacted TLS failure.
- Automatic restore, HA ownership, version canaries and infrastructure cleanup were confirmed.

The retained redacted evidence is `evidence/events-run-d-20260809-0042.jsonl`.

The next server-host experiment requires a publicly trusted certificate for the controlled
nonce hostname or another capture-backed trust model. It should be planned separately before
any recalibration or camera-stream work.
