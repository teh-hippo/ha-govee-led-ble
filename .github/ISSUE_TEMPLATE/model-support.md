---
name: Model support request
about: Request support for a Govee model
labels: []
---

Include the exact SKU (for example `H617A`) in the title and details.
Keep Bluetooth addresses, serial numbers and account details private.

## Device details

Use the device label and Govee app settings for these details.
Enter `unknown` for unavailable values and identify each version number's source.

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

- BLE local-name prefix without the unique suffix (for example `Govee_H617A_`):
- Controller protocol, if shown in diagnostics (`pact_type` / `pact_code`; otherwise `unknown`):
- Sanitised integration diagnostics or debug logs:

In Home Assistant, download diagnostics from the integration entry under **Settings > Devices & services**.
After a failure, download them promptly.
Review diagnostics, screenshots and logs before attaching, removing unique identifiers.

## Testing and follow-up

Test a candidate release and report what works or fails on your device.
Support ships as Experimental first; this request stays open until owner-confirmed Supported shipment.

Report the candidate and hardware/firmware versions, controls tested, visible results and untested areas here.
Include relevant state/readback, reconnect and restoration results.
