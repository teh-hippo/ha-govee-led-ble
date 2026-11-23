---
applyTo: "tools/ble/kaitai/**,custom_components/ha_govee_led_ble/generated_protocol/**,scripts/generate-kaitai.sh"
---

Keep BLE wire structure and uncertainty in Kaitai schemas; never hand-edit generated Python.
Run `make protocol` after `.ksy` changes and `make verify-protocol` to independently regenerate and compare all schemas.
Place unsupported hypotheses only under `tools/ble/kaitai/speculative/` and preserve uncertain bytes without invented validation.
