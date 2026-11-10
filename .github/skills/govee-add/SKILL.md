---
name: govee-add
description: >-
  Add complete Experimental support for a new Govee BLE model. Give it a SKU (and the support-request
  issue if there is one): it builds the device brief from the device evidence, implements full support,
  audits itself, opens the PR, merges it and tells the requester.
license: MIT
---

# govee-add

Argument: a SKU (`/govee-add H6076`), optionally the support-request issue.  Read `.github/skills/govee-shared.md` first.

Goal: complete Experimental support, merged and available in a master release candidate.

Task list:

1. Build the device brief.
2. Create the confirmation issue (wording below) under tracker #442, with the SKU label (create it if missing: colour `5319e7`, description `Govee <SKU> device support`).  Its number goes in the profile's `confirmation_issue`.
3. Implement full support; cover every row of the checklist below or say why a row does not apply.
4. Run `govee-audit` on the result.  Fix each finding as a fixup to the support commit, re-review, and repeat until the audit is clean.
5. Review, commit, `make check`, PR (references the request and the confirmation issue).
6. When the PR is green, merge it to `master`.
7. Follow `CONTRIBUTING.md` release policy: wait for the automatic master candidate containing the merge and verify its workflow and assets.  Do not dispatch another master RC or publish stable.
8. Show the requester reply draft to the operator; after approval, post it on the request (not the confirmation issue), then close the request:
   > Experimental support for `<SKU>` is available in `<master RC tag>`. @`<requester>`, install it through HACS, restart Home Assistant and report feedback on #`<confirmation issue>`.

## Confirmation issue

Title: `<SKU>: owner confirmations by hardware and firmware revision`

```
Tracks Experimental <SKU> BLE support and owner confirmation for each hardware/firmware revision.
Originating support request: #<request>.
Parent tracker: #442.

Please report:
- Printed model, separately identified hardware/firmware versions, integration version and version source.
- Controls tested and visible results: discovery, power/brightness, RGB/segments, eligible Kelvin, scenes/speed, onboard music, DIY/advanced effects and gradual.
- State/readback, reconnect or restoration problems, and features not tested.
- Sanitised diagnostics where useful.

Successful writes or an optimistic UI are not hardware confirmation.
Do not post Bluetooth addresses, serial numbers, account details or other unique identifiers.
Support remains Experimental until owner confirmation and maintainer review.
```

Drop the request line when there is no request.

## New-model file checklist

| File | What it needs |
| --- | --- |
| `custom_components/ha_govee_led_ble/manifest.json` | `bluetooth` `local_name` matchers for every name prefix the device uses (e.g. `ihoment_`, `Govee_`, `Minger_`, `GBK_`, `GVH_`, `GVH<n>`, `GV<n>`, `<SKU>_`).  Without them Home Assistant never discovers it. |
| `custom_components/ha_govee_led_ble/const.py` | `ModelProfile`, including `confirmation_issue`. |
| `custom_components/ha_govee_led_ble/effect_catalogue.py` | `ModelEffectCatalogue` entry. |
| `custom_components/ha_govee_led_ble/scene_catalogues/<SKU>.json` | `uv run python tools/ble/refresh_scene_catalogues.py <SKU>`, before registering the profile. |
| `tools/ble/kaitai/speculative/<sku>_*.ksy` | Exact-model schemas (outside `speculative/` only with recorded device traffic). |
| `scripts/kaitai-runtime-roots.txt`, `scripts/kaitai-runtime-outputs.txt` | Each new `.ksy` root and its generated module. |
| `README.md` | Device-support row: `[🚧 Experimental](<confirmation issue URL>)`. |
| `tests/test_const.py` | SKU-set assertions the profile joins. |
| `tests/test_config_flow.py` | A BLE-name → SKU case per prefix. |
| `tests/test_effect_catalogue.py`, `tests/test_effect_websocket.py` | SKU in the catalogue model lists. |
| `tests/test_profile_wire_invariants.py` | One case per distinct effective profile across revisions. |
| `tests/test_kaitai_protocol.py` | Parse/serialise cases per new schema. |
| `frontend/tests/unit/backend-contracts.spec.ts`, `frontend/tests/unit/catalogue-validation.spec.ts` | SKU in the model lists. |

Often also touched: `protocol_core.py` (generated-module imports), `effect_contracts.py`, `coordinator_status.py`, `generated_protocol_adapter.py`, `music_semantics.py`, `tools/ble/refresh_scene_catalogues.py` with its test, `tests/test_palette_scene_decoder.py` (catalogue fixture count), `tests/test_scenes.py`, a `tests/test_<sku>_*.py` suite, `vulture_whitelist.py`, and `CONTRIBUTING.md` for a new contributor-wide invariant.
`generated_protocol/` and `frontend/tests/fixtures/backend-contracts.json` are gitignored build outputs; never edit or commit them.
