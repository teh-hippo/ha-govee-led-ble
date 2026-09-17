meta:
  id: h6099_wifi_provision_body
  title: H6099 Wi-Fi provisioning common body (documentation only)
  endian: be
doc: |
  SPECULATIVE H6099, support issue #258. Hypothesis: the inherited provisioning
  route uses the common body emitted by Govee Android 7.6.01
  base2light/ble/controller/MultipleWifiController.java:22-105, reached through
  pact_h6099/add/WifiChooseAc.java:31 and
  base2light/ac/AbsBleWifiChooseActivity.java:1503-1515 (under com/govee/).
  Input is the reassembled logical body, not a BLE frame or encrypted envelope.
  Unknowns: exact-device capture, firmware/branch selection, string encoding,
  signed timezone interpretation, and optional API/Matter/security extensions.
  Preserve strings as bytes and the branch-dependent extension as opaque data.
  No runtime provisioning, cloud communication, or exact-device qualification.
seq:
  - id: ssid_len
    type: u1
  - id: ssid
    size: ssid_len
  - id: password_len
    type: u1
  - id: password
    size: password_len
  - id: run_mode
    type: u1
  - id: timezone_hour_raw
    type: u1
  - id: iot_version
    type: u1
  - id: timezone_minute_raw
    type: u1
  - id: extension_raw
    size-eos: true
