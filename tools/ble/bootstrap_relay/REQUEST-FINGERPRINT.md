# Observed H6199 bootstrap request fingerprint

Source: private endpoint experiment on 6 August 2026.

Proven:

- method: `POST`;
- path: `/device/v1/base/config`;
- body length: zero;
- header-name set: `Accept`, `Host`, `envId`, `iotVersion`;
- query-key set: `device`, `sku`, `wifiHardVersion`, `wifiSoftVersion`;
- six retries at about 2.1-second intervals after HTTP 503.

Not retained by the earlier recorder:

- HTTP version;
- header order;
- query-key order;
- header values;
- query values;
- presence or absence of Content-Length;
- connection/framing headers.

Run A therefore records the missing structure without values and forwards new end-to-end
headers/query keys rather than rejecting them. Method, path and empty body remain strict.
