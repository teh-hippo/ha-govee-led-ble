# Run C: controlled MQTT ClientHello

Run C completed successfully on 9 August 2026.

## Boundaries

- One fresh production bootstrap request.
- Replace only the root `mqttAddress` JSON string token.
- Preserve and require production `mqttPort` 8883.
- Resolve the nonce hostname to AI-lab.
- Accept one TCP connection and parse only the first TLS ClientHello.
- Send no TLS response and close before certificate or MQTT exchange.

## Result

- Production returned HTTP 200.
- The single 45-character `mqttAddress` value was replaced by the 42-character nonce.
- The H6199 resolved the nonce and opened TCP/8883 to AI-lab.
- ClientHello advertised TLS legacy version 3.3 in record version 3.1, five cipher suites and
  extensions 0, 13, 22, 23 and 35.
- SNI was present and matched the nonce hostname.
- The probe closed without sending a TLS response.
- Restore association, HA ownership and all four version canaries were confirmed.
- Temporary WLANs, VLAN, policies, listeners, keys and swap override were removed.

The retained redacted evidence is `evidence/events-run-c-20260809-0024.jsonl`.
