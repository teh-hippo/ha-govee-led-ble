# H617A music implementation and evidence

Current integration record, 2026-09-17, supplementing the historical
`h617a-support-findings.md`. Implementation and software verification are complete
for the paths below; expanded playback and rendering remain RC candidates.
This schema-placement work performed no device/HA access or deployment.

The existing tracking issue is [#286, Complete Evidence-Backed Capability Handling
Across Shared Device Workflows](https://github.com/teh-hippo/ha-govee-led-ble/issues/286),
especially its device-specific music semantics section. This is a capability
umbrella, not a newly discovered H617A device-request issue. Fountain's alternative
geometry is also tracked in [#129](https://github.com/teh-hippo/ha-govee-led-ble/issues/129);
its historical “segments” wording does not establish physical IC count.

## Exact APK evidence and field disposition

Java paths are relative to Android **7.6.01** decompilation root
`/workspaces/.govee-static-analysis/h6125-7.6.01/full/sources/com/govee/`.

| Field / contract | Source | Implementation / evidence boundary |
| --- | --- | --- |
| Spectrum/Rolling fixed colour; Energetic no-edit | `dreamcolorlightv1/adjust/ui/MusicFragmentV3.java:44-48,76-81`; `base2light/light/v1/AbsNewMusicFragment.java:756-768,1148-1177` | Explicit exact-model variants. Spectrum/Rolling also have direct-register evidence; Energetic rejects fixed-colour authoring. |
| New selector ID/sensitivity; legacy fixed flag | `dreamcolorlightv1/ble/SubModeMusicV3.java:142-152,190-208` | New suffix has no colour/style authority. Legacy flag is zero/nonzero, not a palette count. Unknown suffix bytes stay uninterpreted. |
| Seven palettes, 1..8 | `base2light/light/v1/AbsNewMusicFragment.java:1011-1075`; `base2light/view/AbsMultiMusicEditDialog.java:132-155,198-217` | Count, RGB list and serialized length change together. Captured presets are defaults, not original resident-state backups. |
| Bloom/Shiny style | `base2light/ble/music/RgbMusicZhanFang.java:17-24,51-85`; `RgbMusicCuiCan.java:18-25,48-76` | Explicit Bloom styles set both speeds (10/80 or 10/20); omitted style preserves both. Shiny sets its brightness pair and preserves speed. |
| Separation | `base2light/ble/music/RgbicMusicFenLi.java:21-30,58-97` | Point independent; gradient also changes speed and requires physical IC metadata. |
| Hopping | `base2light/view/DialogRgbic4YueDong.java:82-142,162-182`; `base2light/ble/music/RgbicMusicYueDong.java:77-94,121-159` | Background and brightness authorable; speed and four piece-range bytes preserved. No invented companion sliders. |
| No-colour sentinel | `base2kt/utils/ColorUtils.java:185-187,418-421,794-796` | No-colour writes RGB 1,1,1; black remains zero. Display equivalence never normalizes stored bytes. |
| Piano | `base2light/view/DialogRgbic4GangQinJian.java:73-79`; `base2light/ble/music/RgbicMusicGangQinJian.java:68-106,123-140` | Gradient independent; key bounds require IC. Off-max is `max(off_minimum, keys//2)`. Unrequested companions survive retained-body edits. |
| Fountain | `base2light/ble/music/RgbicMusicDuiJi.java:13-22,41-106` | Direction/piece geometry requires IC. Captured speed retained; no new speed slider. |
| Day/Night | `base2light/ble/music/RgbicMusicZhouYe.java:59-93,117-130` | KSY `piece_count`; legacy document key `segment_count` retained. Count requires IC; speed/gradient independent. |

## Schema ownership and shared consumers

- `music_body.ksy` keeps the established envelope, palette and tail dispatch.
  Its seven tail types now live once in `speculative/h617a_control_payload.ksy`.
  Newly generalized Bloom no-rhythm speed, Shiny speed, Hopping companions,
  Piano speed/off-minimum and Fountain piece length are **APK-backed**, not
  promoted by existing preset captures. Grouping the other tail fields there
  preserves their existing capture evidence and semantic names.
- The same speculative payload schema owns **AA0F**. Direct H617A HW3.01.01 /
  FW3.02.24 evidence establishes value 15; the positive Java signed-byte boundary
  and ignored suffix come from `LightNumController.java:12-25`. The parent status
  root dispatches directly to it; the query reuses the existing zero body.
  Diagnostics never convert AA0F into IC or logical-segment geometry.
- `speculative/h617a_command_ack.ksy` owns the new ordinary/A3 ACK parser.
  Existing A3 transport framing remains in the parent command schema.
- H617E structurally shares the H617A music/status/ACK codecs, but retains its
  independently declared pre-expansion variants, palette permissions, defaults,
  ordering and IC policy. Its upload-ACK requirement remains false. This work
  establishes no expanded H617E product qualification.
- H6099 retains `speculative/h6099_music_parameters.ksy`, its own ACK schema,
  defaults and whole-body IC policy. Shared Java producers and semantic helpers
  do not authorize H617A controls on H6099. The explicit Bloom pair correction
  applies to both serializers using the same attributable Java setter.

The two new speculative roots are explicitly selected in
`scripts/kaitai-runtime-roots.txt`; outputs are generated canonically. Public
semantic Python APIs and returned named fields remain stable; generated class
ownership and ACK parser diagnostic identity now identify the extracted schemas.
Parent envelopes importing speculative payloads do not promote those payloads.
Official-app captures, representative parser tests, owner qualification and
enabled-path documentation remain required by `CONTRIBUTING.md:132-135`.

## Completed runtime integration

H617A declares upload-before-selector and `music_requires_upload_ack=True`.
`async_write_effect_sequence` supports `require_upload_ack`, `upload_ack_index`
and connection-bound `writer`. Saved application and preview use this boundary.

The ACK future is armed after transforms/guards immediately before the **final
physical upload attempt**, accepting even a synchronous notification from that
write. Ordinary/V1 native-DIY status is byte 2; V2 music status is byte 3
(`AbsSingleController`, `AbsMultipleControllerV1`, `AbsMultipleControllerV2`).
Only a positive matching result permits the selector. Missing/negative replies,
connection loss, profile changes and cancellation fail; pending state is cleared.
Normal radio/timeout retries restart the transaction; preview writers never
reconnect or retry. Per-packet state is installed at the physical-write boundary.

**Correlation limit:** `AbsController.isSameController` matches protocol/subtype,
not a transaction ID. Old subscriptions and early/unrelated ACKs cannot release
the gate, but a delayed same-subtype ACK during a later final attempt is
indistinguishable. ACK establishes neither rendering nor resident-body equality.

`coordinator.music_body` exposes retained complete bytes only for their mode.
The first fragment invalidates prior body knowledge; a candidate is installed
only after sequence success and an unchanged retention revision. Attempted-upload
failure/cancellation clears body/palette. Reconnection and mode-provenance changes
invalidate retention. A same-mode selector cannot reveal another controller's
changed resident body.

Prior state serializes optional body bytes as validated hex. Recovery uses
`prepare_music_body_writes` and replays them verbatim, without preset/geometry
recompilation. Missing bodies remain unknown. Decoded fields are retained display
values, never fresh observations; full-body equality is not claimed by recovery.
`_send_music_params` requires a retained body and edits only requested fields;
explicit style changes update the complete pair. Sensitivity-only preparation
remains selector-only. Physical-boundary IC guards inspect actual requested keys,
including compiled defaults. Logical segment count and AA0F never substitute for IC.

## Verification and remaining qualification

Focused regressions cover palette lengths, companion preservation, exact-profile
permissions, raw-body persistence/replay, explicit Bloom pairs and failure
provenance. `test_upload_ack.py` exercises the real parser and sequence boundary
with fake notifications, including preview/saved application and negative results;
tests that isolate music state may still use a fake successful ACK boundary.
`test_h617a_light_count.py` checks generated payload ownership and signed bounds.

Schema-placement checks on 2026-09-17:

- `make protocol` and `make verify-protocol`: passed, including **132 parser tests**
  and byte-for-byte canonical runtime-output comparison.
- Focused music/ACK/count/DIY/segment-Kelvin/restoration selection: **534 passed**.
- Ruff check/format for the adapter and three changed test files: passed.
- Mypy for all integration modules plus the music/count test files: passed
  (**108 source files**). Whole-repository mypy reported four errors in concurrent
  parent-owned `tests/test_effect_preview.py:1205,1223,1225,1227` (untyped events
  list and insufficient compiled-type narrowing). Including `test_upload_ack.py`
  also reaches that file through its preview-test imports. No schema/adapter
  typing error was reported. The parent owns those fixes and final `make check`.

RC installation/testing is authorized for cupboard-skirt H617A only; this record
does not claim it occurred. Expanded A3 playback, rendering, alternative physical
geometry and old revisions remain unqualified. RC testing alone is not an
official-app capture and does not promote speculative schemas.
