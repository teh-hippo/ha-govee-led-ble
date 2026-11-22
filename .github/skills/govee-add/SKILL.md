---
name: govee-add
description: >-
  Add complete Experimental support for a new Govee BLE model. Give it a SKU (and the support-request
  issue if there is one): it builds the device brief from the device evidence, implements full support
  through shared capability-driven paths, audits itself, opens the PR, merges it and tells the requester.
license: MIT
---

# govee-add

Argument: a SKU, optionally its support-request issue.
Read `.github/skills/govee-shared.md` first.

Goal: complete Experimental support, merged and available in a master release candidate.

Task list:

1. Use the exact-SKU request for implementation and owner verification.
   Create a missing request with `.github/ISSUE_TEMPLATE/model-support.md`; consolidate existing threads under `CONTRIBUTING.md`.
   Set `confirmation_issue` and the README Experimental link to that request.
2. Build the complete revision-aware device brief and map it onto existing declarations, codecs and shared operations.
   Cover each checklist row or explain its applicability.
   Extend shared machinery where evidence demonstrates a gap.
3. Run `govee-audit` for completeness, special treatment and implementation correctness.
   Close coupled findings under canonical acceptance policy.
   Its fresh-context correctness review can satisfy independent acceptance review.
4. Reconcile upstream at readiness, commit, pass `make check` and open the PR referencing the request.
   Keep the request open for hardware confirmation.
5. Merge the green PR to `master`, then verify the automatic master candidate's workflow and assets.
6. Show the requester reply draft to the operator and post after approval:
   > Experimental support for `<SKU>` is available in `<master RC tag>`.
   > @`<requester>`, install it through HACS, restart Home Assistant and report hardware/firmware versions, controls tested and visible results here.
   `govee-resolve` handles confirmed support and eventual closure.

## New-model integration checklist

Use existing shared contracts at these integration points.

Under `custom_components/ha_govee_led_ble/`:

- `manifest.json`: `bluetooth` `local_name` matchers for every evidenced name prefix.
  Examples: `ihoment_`, `Govee_`, `Minger_`, `GBK_`, `GVH_`, `GVH<n>`, `GV<n>`, `<SKU>_`.
- `const.py`: complete `ModelProfile` with `confirmation_issue`.
- `effect_catalogue.py`: `ModelEffectCatalogue`.
- `scene_catalogues/<SKU>.json`: run `uv run python tools/ble/refresh_scene_catalogues.py <SKU>` before profile registration.

Repository files:

- `tools/ble/kaitai/speculative/<sku>_*.ksy`: exact-model schemas; recorded traffic qualifies schemas outside `speculative/`.
- `scripts/kaitai-runtime-roots.txt` and `scripts/kaitai-runtime-outputs.txt`: new roots and generated modules.
- `README.md`: `[🚧 Experimental](<confirmation issue URL>)` device row.
- Existing discovery, profile, catalogue, protocol and frontend suites: shared parametrisation for distinct capabilities, prefixes and wire shapes.

Update `CONTRIBUTING.md` for contributor-wide invariants.
Build `generated_protocol/` and `frontend/tests/fixtures/backend-contracts.json` locally; both remain gitignored.
