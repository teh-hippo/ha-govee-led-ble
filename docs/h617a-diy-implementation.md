# H617A native DIY implementation ledger

Current integration record, 2026-09-17. Native-template evidence is Android
**7.6.01** source plus software checks, not qualified rendering. This work made
no device/HA contact or deployment. The existing capability-support umbrella is
[#286](https://github.com/teh-hippo/ha-govee-led-ble/issues/286); no new exact-model
request issue is implied. Cupboard-skirt H617A RC testing is authorized separately.

## Implemented path

`effect_catalogue.py` declares seven exact-H617A templates under
`template:native-diy:501` through `template:native-diy:507`. They use the existing
`advanced` content kind, canonical `LayeredEffect.layers`, and an optional
`native_diy` selector identity. This identity survives catalogue defaults,
library save/import, frontend decoding/cloning/editing, and compilation. A
different requested selector or target SKU is rejected. H617E does not inherit
these templates or the APK-backed H617A Chase limit.

The compiler uses `encode_workshop_effect()` solely as the existing generated
**layer-container codec**, then `fragment_a3(2, payload)`. Activation is the
template's **own scene selector**, not Workshop 401, Type04 DIY 24, or Forest.
`CompiledEffect` returns `activation_mode=CUSTOM`, `selector_kind="scene"`,
`diy_code=501..507`, `expected_effect=None`, and evidence code
`native_diy_positive_ack_required`. Its packet tuple expresses upload then
selector; both saved application and preview now enforce the asynchronous ACK
barrier in `coordinator.py:async_write_effect_sequence`.

### APK attribution

All paths below are relative to
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources/com/govee/`.

* `dreamcolorlightv1/adjust/v1/UiV3.java:402-404` →
  `dreamcolorlightv1/adjust/Diy.java:233-336`: reachable fixed DIY version 2.
* `base2light/ac/diy/DiyM.java:1087-1117`: exact 501..507 selector mapping.
* `base2light/ble/ScenesOp.java:514-523` →
  `ble/controller/MultiDiyTempalteController.java:9-12`: A3 subtype **02**.
* `dreamcolorlightv1/adjust/v1/BleOpV3.java:315-337`: failed upload reports
  failure; successful upload sends `SubModeScenes` for its template code.
* `dreamcolorlightv1/ble/SubModeScenes.java:38-41,63-69`: scene submode 4,
  little-endian u16 selector. Existing scene KSY/builder owns that structure.

## Seven candidates and named editor controls

The stored seeds are verbatim APK presets, **not geometry observations or claimed
factory defaults for this device**. Named controls update the same canonical
layers; the advanced fields remain available. APK preset palettes/ranges may
differ from a freshly authored app effect. Imports are not silently truncated.

| Selector | Template / APK producer in `base2light/ac/diy/v2/ParamsV2.java` | Applied named controls |
| --- | --- | --- |
| 501 | Brilliant / Colorful, seed `f54953d`, 1304-1329 | Background layer 0; 4..8 adorn colours interleaved across layers 1/2; colour speed 0..255 on 1/2; gradient uses retention 50; off restores seed retentions 250/10/10. Brightness low/high on 1/2 and background `max(20, low)`. |
| 502 | Colorful Sky, `f54956g`, 1719-1759 | 2..8 colours interleaved across two layers; speed 150..255 affects colour and brightness speed; brightness 50..255 changes upper scope; random star minimum/maximum. |
| 503 | Meteor, `f54955f`, 1521-1534 | Palette, whole-layer movement speed 200..255, direction changes area start 0/9, brightness order 2/0 and whole-layer direction 0/2 together. |
| 504 | Meteor Shower, `f54954e`, 1537-1588 | 3..8 colours interleaved over three layers; whole-layer speed 200..255; direction updates starts 0/4/7 or 9/5/2, pattern orders and movement directions together. Selection quantity depends on physical IC count / 5. |
| 505 | Shine, `f54957h`, 1699-1716 | Background layer 1; 1..8 colours on layer 0; speed 200..245 changes colour, brightness and selected-area movement speed; brightness range and background `max(20, low)`. |
| 506 | Bloom DIY, `f54958i`, 1170-1237 | Two 2..8-colour groups (bloom on 0/1, moving on 2/3); brightness 50..255 changes upper scope; clockwise/counterclockwise/two-way layout follows physical IC geometry, including inactive black layer in one-way modes. |
| 507 | Stack, `f54959j`, 1762-1778 | Independent 1..8 moving/stack palettes on layers 1/0; brightness 25..255 changes both scope endpoints; opposite selected-area movement directions. No invented speed slider. |

UI ranges come from fully reviewed
`base2light/ac/diy/v1/ViewDiy{Colorful,Sky,Meteor,MeteorRain,Shine,Bloom,Stack}Edit.java`.
Colorful/Shine brightness range has app interval 76; named sliders retain that
interval. A no-colour entry is preserved as its RGB bytes; no black/transparent
normalization is introduced. Generic advanced edits are structural candidates,
not a claim that every combination is an app-authored preset.

Same-length palette edits preserve the existing layer/slot assignment, including
Meteor Shower's actual 3/1/1 seed. Explicit length changes redistribute by the
APK authoring algorithm. The regression edits all five original seed positions;
a one-colour change no longer moves an untouched colour to a sibling layer.

### Physical IC unknown: field-specific gates

Neither logical `segment_count=15` nor `AA0F=15` supplies physical IC geometry.
Seeds stay usable as explicit presets; unrelated palette colours, brightness and
speed edits remain usable when geometry is unknown.

| Dependent control | Exact APK justification | Implementation |
| --- | --- | --- |
| Sky star size | `ViewDiySkyEdit.java:177-187`: maximum `min(25, IC*4/5)`; new app default `min(25, IC*2/5)`. `ParamsV2.java:615-617` writes max then min. | Disable star/selection edits without IC; preserve seed pair; validate known-IC edits against the bound. |
| Meteor palette size | `ViewDiyMeteorEdit.java:156-166`: `min(max(1, IC*2/10),8)`. Its initial `g()` population still uses 8; this source inconsistency is not firmware proof. | Unknown IC freezes palette **length**, not RGB edits; known-IC length changes obey the computed ceiling. |
| Meteor Shower selection | `ParamsV2.java:1545-1552`: all three continuous quantities are `IC/5`. | Unknown IC preserves seed selections. Backend admits changed selections only with known IC and that quantity. |
| Bloom direction/layout | `ParamsV2.java:1181-1227`: two-way uses half IC per moving layer, one-way uses all IC plus an inactive one-IC black layer. | Disable direction and dependent moving-layer area/selection edits without IC; independent colours/brightness remain available. Known IC enables the named producer. |

Selection quantities retained from seeds do not establish the physical strip's
size. Automatic conversion of seed geometry to a target's count is deliberately
not performed on unrelated edits. Complete original device payload readback and
settings-exact restoration are still unknown.

## Shared canonical controls / KSY review

`govee_shared.ksy` names the following generated instances; `make protocol`
regenerates outputs canonically. No generated Python was hand-edited.

* **Layer brightness**, not brightness-pattern order: high-nibble algorithm
  0..2 and low-nibble type 0..3 (`ScenesRgbIC.java:4227-4266`). Both have editor
  controls. Numeric labels avoid inventing algorithm behaviour names. Legacy
  `brightness_gradient` plus `unknown_flags` remain the lossless storage split;
  canonical properties expose `brightness_algorithm` / `brightness_type`.
  Other nibble values stay preserved until explicitly edited.
* Selection 0/1: named BE u16 quantity, including nonzero high bytes. Selection 2:
  random maximum/minimum bytes. Selection 3: piece/gap IC counts
  (`ParamsV2.java:735-743,978-992`). No field is relabelled as HA segment geometry.
* Distribution method is the low **four** bits; direction is bit 7;
  bits 4..6 are `extensions`, preserved through editing and encoding
  (`ParamsV2.java:339-384,414-426`). Method 3 is segment distribution with gradient.
  Old `method=0..127` documents are losslessly normalized. Library import accepts
  the historical content hash only after independently checking the old packed
  representation; corrupt hashes still fail.
* Pattern-order bytes, layer/movement unknown fields, source padding and excess
  bytes retain their existing preservation behaviour. No speculative brightness
  algorithm names or new wire enums/constraints were invented.

H617A Type04 Chase uses its existing per-family palette limit **3** and existing
three-colour RGB default branch. Old seven/eight-colour imports remain saved
intact but fail target application eligibility; nothing is truncated.

## Completed runtime integration and speculative placement

`native_diy_positive_ack_required` makes saved application and preview enforce
upload → positive A3 result → own scene selector. The future is armed after
transforms/guards immediately before the final physical upload attempt. Missing,
negative, early, unrelated or old-subscription ACKs cannot activate the selector.
Connection/profile changes fail closed. Normal radio/timeout retries restart the
transaction; injected preview writers retain their connection and never retry.

Native DIY uses **V1 result byte 2**, through `MultiDiyTempalteController` →
`AbsMultipleControllerV14DiyTemplate` → `AbsMultipleControllerV1.q/j`. Music uses
V2 byte 3. These definitions now live once in
`tools/ble/kaitai/speculative/h617a_command_ack.ksy`. Ordinary positive replies
have direct-device evidence; A3/negative replies and unknown tails lack the
official-app capture/owner qualification required for promotion.

**Correlation limit:** APK `AbsController.isSameController` compares only
protocol/subtype. A delayed same-subtype result arriving during a later final
attempt cannot be distinguished from that attempt's result. Successful GATT
writes, positive ACKs and selector readback do not prove rendering or resident
body equality. Deployment records retain scene-selector authority and the
compiler's explicit readback/rendering evidence codes; exact native-DIY body
restoration remains unqualified.

The established `workshop_body.ksy` layer container and command scene-selector
layout remain shared. No duplicate seven-template wire layout is introduced.
`govee_shared.ksy` retains lossless aliases for already-modelled fields with APK
attribution; newly exposed control behaviour remains a candidate. The related
generalized music tails and AA0F body are extracted to
`speculative/h617a_control_payload.ksy`, imported directly by their parent roots.
See [music evidence](h617a-music-implementation.md) for exact fields and consumers.
H617E shares structural codecs but does not inherit native templates, new Chase
permissions or upload-ACK policy. H6099 keeps its independent speculative roots
and product policy; common layer/Java structures establish no new SKU support.

The catalogue, template-default loader, persisted identity, generated contract
fixture and Advanced browser/editor paths are wired. `panel.ts` passes physical
IC metadata separately from the logical segment visualization. Unknown IC retains
the field-specific gates above. Final frontend build and full `make check` remain
the parent's release checks, not missing runtime integration.

Each 501..507 body/selector, directions, palette/brightness edits and restoration
still need owner qualification with original payloads and visual observation.
An exact-model RC may contain these explicitly selected speculative roots for
the authorized cupboard-skirt tests. Promotion additionally requires attributable
official-app captures and enabled-path documentation per `CONTRIBUTING.md`.

## Focused proof ledger

* `tests/test_h617a_native_diy.py`: all seven APK seed byte round-trips,
  save/import identity, exact A3 fragment equality and own selectors, wrong-slot/
  wrong-SKU rejection, generated nibble/BE/extension fields, sibling/excess
  preservation, IC-unknown dependent rejection vs independent edit, Chase legacy
  preservation and historical hash validation.
* `frontend/tests/unit/native-diy.spec.ts`: all seven named palette producers,
  Stack direction/brightness, Bloom half-count >255, Sky geometry bounds,
  independent brightness nibble edits, extension retention, clone/controller/
  default-detail decode identity.
* `tests/test_upload_ack.py`: real generated ACK parser and transaction boundary,
  preview/saved application, negative/missing results and callback races using
  software notifications. These are scheduling proofs, not hardware evidence.
* Existing layered/domain/catalogue tests cover the shared container. The schema
  extraction uses canonical protocol generation and verification plus focused
  Python tests, Ruff and mypy. Full `make check` belongs to the parent.

The 2026-09-17 extraction checks passed canonical generation/comparison, **132
parser tests**, **534 focused integration tests**, Ruff, and integration/music/count
mypy (**108 files**). Whole-repository mypy found four parent-owned preview-test
typing errors; see the [music check record](h617a-music-implementation.md#verification-and-remaining-qualification).
