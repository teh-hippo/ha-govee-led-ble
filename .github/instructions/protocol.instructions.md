---
applyTo: "tools/ble/kaitai/**,custom_components/ha_govee_led_ble/generated_protocol/**,scripts/generate-kaitai.sh"
---

Use the [protocol authority in CONTRIBUTING](../../CONTRIBUTING.md#capability-and-protocol-authority).
Edit Kaitai sources, not generated Python; similar byte layouts alone do not establish equivalent behaviour.
Run `make protocol` after `.ksy` changes and `make verify-protocol` to independently regenerate and compare all schemas.
Place unsupported hypotheses only under `tools/ble/kaitai/speculative/` and preserve uncertain bytes without invented validation.
