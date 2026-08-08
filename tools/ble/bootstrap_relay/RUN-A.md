# Run A: unchanged production relay

The procedure below was executed successfully on 8 August 2026.

## Execution result

- Production returned HTTP 200 to the single bootstrap request.
- The 3,347-byte response payload was relayed unchanged.
- Attributable next-stage DNS began immediately after the response.
- The response schema contained MQTT connection fields and certificate material; values were
  not retained.
- Windows BLE disconnected after the first provisioning acknowledgement, but independent
  WLAN association and subsequent TLS traffic proved the write had committed.
- The restore WLAN was rotated to a new in-memory passphrase, association was confirmed, HA
  returned loaded and all temporary infrastructure was removed.
- Firmware, hardware and both subordinate versions matched the pre-run canaries.

## Success

The production response is relayed unchanged and the H6199 subsequently attempts a
next-stage DNS lookup attributable to that response.

Retry cessation alone is not success.

## Hard boundaries

- One upstream production request per run.
- Two planned BLE provisioning writes, three absolute maximum.
- No response mutation.
- No client-certificate request.
- No MQTT CONNECT.
- No factory reset.
- No raw production response on disk/stdout/stderr.

## Preconditions

1. Offline suite and pause gate pass.
2. User explicitly approves live execution and is physically present.
3. Calibration preservation is either established with fixed-pattern photographs across an
   ordinary power cycle, or the user explicitly accepts repairing any reset in the Govee app.
4. Firmware, hardware and subordinate version canaries are recorded.
5. Relay host matches the tested Python/OpenSSL versions.
6. Device-facing RSA certificate is fresh and uses the tested cipher profile.
7. The real UniFi lifecycle has been rehearsed: network, both WLANs and five relay-service
   allow policies apply, validate and tear down.
8. AI-lab runs with swap disabled during the relay and its local DNS, NTP and TLS listeners
   pass the live probe.
9. UniFi reports the lab network with WAN disabled, network isolation enabled, IPv6 off,
    relay DNS/NTP via DHCP, and the restore WLAN on Default.
10. Wireless association and the isolation data path are confirmed immediately after the
    H6199 joins; the Proxmox uplink is access-only and cannot honestly emulate that WLAN.

## Sequence

1. Start structured-event sink.
2. Start non-forwarding DNS observer.
3. Start device-facing relay.
4. Resolve production once; require a public address.
5. Confirm upstream request and response counters are zero.
6. Refresh the unused prewarmed TLS connection every three seconds until the request arrives.
7. Validate the live UniFi state and local DNS/NTP/TLS listeners.
8. Generate random single-use 7-character SSIDs and 8-character ASCII WPA2 passphrases in
   memory.
9. Show `wifi_provision.py compare` output without revealing values.
10. Release the Home Assistant entry with the local HA-platform hand-back trap.
11. Prove the BLE link is free by read-back.
12. Provision the lab SSID and controlled API.
13. Require `a1 11 00` and `ee 11 00`.
14. Require independent UniFi association to the random lab SSID.
15. Accept the first config POST.
16. Automatically send exactly one upstream request.
17. Extract redacted response schema after receiving it.
18. Relay payload automatically; no human gate.
19. Reuse the in-memory response for device retries.
20. Observe next-stage DNS.
21. Stop after the 180-second wall-clock budget.

## Expected events

1. `upstream_prewarmed`
2. `tls_accepted`
3. `request_shape`
4. `upstream_fetched`
5. `response_schema`
6. `response_relayed`
7. zero or more retry `request_shape` / `response_relayed`
8. `dns_match`
9. `stop`

## Stop immediately

- TLS cipher/version differs from the parity test.
- Request method/path/body differs.
- Required query keys disappear or duplicate.
- Upstream call counter exceeds one.
- Production certificate/hostname validation fails.
- Redirect, unexpected response framing or size limit.
- Raw response or sensitive value reaches an event/error/file.
- H6199 reaches an unexpected production destination.
- Version canary or calibration changes.
- Home Assistant ownership is lost.
- Association or restore fails.
- Six attempts are exhausted without attributable progression.

## Restore

1. Keep the isolated network active.
2. Use the second planned provisioning write:
   - known-good temporary SSID;
   - production API URL.
3. Require `ee 11 00` and independent association.
4. Observe production bootstrap metadata without reading another response.
5. Hand BLE ownership back to Home Assistant.
6. Verify all entries loaded and controls responsive.
7. Verify version canaries and calibration fingerprint.
8. Remove and permanently retire the temporary SSID name.
9. Remove relay, resolver, observer, VLAN, DNS and firewall state.
10. Best-effort zero the response cache and terminate the short-lived relay process.
11. Retain redacted facts only.
12. Record that the device is provisioned to the now-retired absent restore SSID.

If restore fails, retain the isolated lab network with WAN denied, restore HA BLE ownership,
record `restore outstanding`, and do not delete the only network the device can join.
