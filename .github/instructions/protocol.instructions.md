---
applyTo: "tools/ble/kaitai/**,custom_components/ha_govee_led_ble/generated_protocol/**,scripts/generate-kaitai.sh"
---

Keep BLE wire structure and uncertainty in Kaitai schemas; never hand-edit generated Python.
Kaitai selects wire shape; profiles and semantic declarations select behaviour.  Do not teach shared parsers or builders exact SKUs.
Keep required model differences in explicit profiles and narrow codecs selected by declared grammars or typed semantics.
Do not infer semantic equivalence from a similar byte layout or reuse an adjacent profile flag for a different observable consequence.
Run `make protocol` after `.ksy` changes and `make verify-protocol` to independently regenerate and compare all schemas.
Place unsupported hypotheses only under `tools/ble/kaitai/speculative/` and preserve uncertain bytes without invented validation.
