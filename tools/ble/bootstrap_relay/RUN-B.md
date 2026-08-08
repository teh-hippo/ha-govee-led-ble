# Run B: mqttAddress mutation

Run B completed successfully on 8 August 2026.

## Boundaries

- One fresh production bootstrap request.
- Replace only the root `mqttAddress` JSON string token.
- Derive the replacement hostname from the run ID and controlled device-facing domain.
- Return NXDOMAIN for the nonce hostname.
- Stop immediately after attributable nonce DNS.
- No MQTT connection, client-certificate use or additional response mutation.

## Result

- Production returned HTTP 200 with a 3,347-byte JSON response.
- The single 45-character `mqttAddress` value was replaced by the 42-character nonce.
- The relayed body was 3,344 bytes; all other response bytes were preserved.
- The H6199 queried the nonce hostname once.
- The DNS observer returned NXDOMAIN and the relay stopped with reason `dns_match`.
- One upstream fetch, one mutation event and one response relay were recorded.
- Restore-WLAN association and HA ownership were confirmed.
- Temporary WLANs, VLAN, firewall policies, listeners, keys and swap override were removed.
- Firmware, hardware and both subordinate version canaries matched the baseline.

The retained redacted evidence is `evidence/events-run-b-20260808-2355.jsonl`.
