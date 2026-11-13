---
name: govee-add
description: >-
  Add complete Experimental support for a new Govee BLE model. Give it a SKU (and the support-request
  issue if there is one): it builds the device brief from the device evidence, implements full support
  through shared capability-driven paths, audits itself, opens the PR, merges it and tells the requester.
license: MIT
---

# govee-add

Argument: a SKU, optionally the support-request issue.  Read `.github/skills/govee-shared.md` first.

Goal: complete Experimental support, merged and available in a master release candidate.

Task list:

1. Build the device brief.
2. Create the confirmation issue (wording below) under tracker #442, with the SKU label (create it if missing: colour `5319e7`, description `Govee <SKU> device support`).  Its number goes in the profile's `confirmation_issue`.
3. Map the device brief onto existing capability declarations, codecs and shared operations before implementing.
   Follow the shared design workflow; cover every row of the checklist below or say why a row does not apply.
   Complete support should normally add product declarations and evidenced codecs, not another entity, coordinator, editor or recovery path.
   Where existing machinery cannot express a capability, correct or extend that machinery for all affected callers; keep an override only for evidenced semantic differences.
4. Run `govee-audit` on both completeness and special treatment in the result.
   Fix supported root causes as fixups to the support commit, remove superseded code, re-review, and repeat until no actionable findings remain.
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

## New-model integration checklist

These are integration points, not a requirement to add a new handler or test file for each device.
Follow existing shared contracts rather than copying the nearest model's implementation.

| File | What it needs |
| --- | --- |
| `custom_components/ha_govee_led_ble/manifest.json` | `bluetooth` `local_name` matchers for every name prefix the device uses (e.g. `ihoment_`, `Govee_`, `Minger_`, `GBK_`, `GVH_`, `GVH<n>`, `GV<n>`, `<SKU>_`).  Without them Home Assistant never discovers it. |
| `custom_components/ha_govee_led_ble/const.py` | `ModelProfile`, including `confirmation_issue`. |
| `custom_components/ha_govee_led_ble/effect_catalogue.py` | `ModelEffectCatalogue` entry. |
| `custom_components/ha_govee_led_ble/scene_catalogues/<SKU>.json` | `uv run python tools/ble/refresh_scene_catalogues.py <SKU>`, before registering the profile. |
| `tools/ble/kaitai/speculative/<sku>_*.ksy` | Exact-model schemas (outside `speculative/` only with recorded device traffic). |
| `scripts/kaitai-runtime-roots.txt`, `scripts/kaitai-runtime-outputs.txt` | Each new `.ksy` root and its generated module. |
| `README.md` | Device-support row: `[🚧 Experimental](<confirmation issue URL>)`. |
| Existing discovery, profile, catalogue, protocol and frontend contract suites | Register new declarations and cover each distinct effective capability contract, discovery prefix and wire shape through shared parametrisation. |

Runtime changes are justified by missing shared behaviour or a new evidenced wire shape, not by adding a SKU alone.
Extend existing protocol adapters, semantic handlers and shared tests only where the device brief demonstrates a gap.
Update `CONTRIBUTING.md` only for a new contributor-wide invariant, not a recipe for this device.
`generated_protocol/` and `frontend/tests/fixtures/backend-contracts.json` are gitignored build outputs; never edit or commit them.
