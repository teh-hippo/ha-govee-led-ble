# Threat model

## Protected assets

- H6199 identity and request query values.
- Production bootstrap response.
- Any returned private key, certificate, endpoint, client ID or topic.
- Home Assistant ownership and BLE availability.
- Existing camera calibration.
- UniFi and AI-lab infrastructure.
- Govee account/device cloud state.

## Trust boundaries

1. H6199 to device-facing relay: self-signed TLS accepted by the device.
2. Relay to production: public PKI, fixed hostname and verified TLS.
3. Relay memory to structured events: values must be removed before serialisation.
4. Relay host to filesystem/process environment: no raw data, key log, core dump, argv or
   environment secret.
5. H6199 VLAN to the network: only explicitly permitted local services.

## Primary threats and controls

| Threat | Control |
| --- | --- |
| Wrong TLS profile creates a false negative | TLS 1.2 only, RSA-2048, `AES256-SHA256`, parity test |
| Offline tests contact production | whole-suite loopback egress guard and injected resolver |
| Six retries issue six production credentials | single-flight run cache and one-call test |
| HTTP library mutates request/response | raw TLS sockets and hand-written HTTP/1.1 |
| Chunking/compression changes payload | no transparent decode, de-chunk only, raw payload identity tests |
| Response leaks through logs | pre-serialisation schema extraction, enum event fields, raw-byte refusal |
| TLS pcap becomes decryptable | remove `SSLKEYLOGFILE`, assert keylog disabled |
| Secrets persist in core/stdout/env | `RLIMIT_CORE=0`, stdout not persistent, no env/argv secrets |
| DNS rebinding reaches local address | resolve once, public-address assertion, connect to resolved address |
| Failed process leaves resources | intent-first shell state, incremental UniFi ownership file, signal-aware cleanup and fresh-shell teardown |
| Restore failure strands device state | two-write plan, isolated recovery-debt state, factory reset forbidden |
| Calibration loss | visual fingerprint and ordinary power-cycle gate before live provisioning |

## Residual risks

- CPython, OpenSSL, JSON objects, rendered response copies and kernel buffers may retain
  response material until process exit. Bytearray clearing is best effort only.
- Production bootstrap may be state-changing even with one request.
- Production may reject a request forwarded from a different source IP or with rebuilt
  transport metadata.
- Response may be signed or integrity-protected.
- Device response timeout remains unknown; upstream pre-warm reduces but cannot eliminate it.
- A stale production prewarm can still fail after the one HTTP request is sent. The tool
  refuses a second production request rather than violating the one-request invariant.
- The access-only Proxmox uplink cannot emulate the wireless VLAN. UniFi configuration is
  asserted before device access; association and isolation are confirmed when the H6199 joins.
- UniFi's `internet_access_enabled=false` and network isolation perform the deny. The current
  controller does not accept the attempted subnet-scoped block policies, so no live
  denied-egress event is claimed.
- Deleting an SSID does not clear the device credential. The terminal state remains
  provisioned to a retired absent SSID.

## Phase 1 claim

The tooling is proven against fabricated loopback peers, through real device-free
UniFi/AI-lab lifecycle rehearsals and through live Run A and Run B executions. Run A proved
unchanged relay acceptance; Run B proved the H6199 honours a mutated `mqttAddress` through
nonce DNS; Run C proved controlled TCP/TLS ClientHello routing. Run D sent a server
certificate without requesting a client certificate and the device closed during the
handshake. No run obtained a client certificate, MQTT CONNECT or CONNACK.
