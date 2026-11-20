---
name: Model support request
about: Request support for a Govee model
labels: []
---

Include the exact SKU (for example `H617A`) in the issue title and details.  Do not post the Bluetooth address, serial number or account details.

## Device details

The device label and Govee app's device settings provide most of these details.  Enter `unknown` for anything you cannot reasonably obtain, and identify the source of version numbers.

- SKU printed on the device:
- Product name and public product/manual link:
- Firmware version:
- Hardware version:
- Version source (Govee app, integration diagnostics or unknown):
- Does the Govee app offer an update?
- Integration and Home Assistant versions, if installed:
- Bluetooth connection (local adapter or ESPHome proxy):

## Behaviour

- Controls available in the Govee app:
- Controls that already work or fail in this integration, if tested:

## Additional evidence, if available

- BLE local-name prefix without the unique suffix (for example `Govee_H617P_...`):
- Sanitised integration diagnostics or debug logs:

In Home Assistant, download diagnostics from the integration entry under **Settings > Devices & services**.
After a failure, download them promptly and review them before attaching; diagnostics are not guaranteed anonymous.
Remove unique identifiers from screenshots and logs too.

## Testing and follow-up

Please expect to try a candidate release and report what works or fails on your device.  Real-device verification is needed before support can be marked Supported.
Implementation can merge and ship as Experimental first; this request stays open for feedback until confirmed support ships.

When testing, comment here with the candidate version, hardware/firmware versions, controls tested, visible results, and anything not tested.
Include state/readback, reconnect or restoration problems where relevant; an accepted write or optimistic UI alone is not hardware confirmation.
