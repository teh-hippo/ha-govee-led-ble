meta:
  id: h6199_wifi_body
  title: Govee H6199 Wi-Fi provisioning body, reassembled from a1 11 frames
  endian: be
seq:
  - id: ssid_len
    type: u1
  - id: ssid
    size: ssid_len
    type: str
    encoding: UTF-8
  - id: password_len
    type: u1
  - id: password
    size: password_len
    type: str
    encoding: UTF-8
  - id: run_mode
    type: u1
  - id: tz_hour
    type: u1
  - id: iot_version
    type: u1
  - id: tz_minute
    type: u1
  - id: api_len
    type: u2
  - id: api
    size: api_len
    type: str
    encoding: UTF-8
  - id: matter_wifi_flag
    type: u1
  - id: security_type
    type: u1
