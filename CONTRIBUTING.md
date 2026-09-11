# Contributing

## Requesting support for another model

Open one GitHub issue for the exact model.  Include:

- the SKU printed on the device;
- the BLE local-name prefix with its unique suffix removed, for example `Govee_H617P_...`;
- firmware and hardware versions;
- whether the Govee app offers an update;
- which controls already work or fail; and
- whether you can install one model-specific prerelease and report manual results.

Do not post the Bluetooth address, serial number, account details, or other unique identifiers.

## Project structure

- `custom_components/ha_govee_led_ble/const.py` owns the exact-model `ModelProfile` registry.  Profiles declare product capabilities and runtime policy; `command_grammar` and `status_grammar` independently select compatible outbound and inbound protocols.
- `tools/ble/kaitai/**/*.ksy` is the only BLE wire-structure source.  Generated modules under `generated_protocol/` are build outputs and are never edited manually.
- `generated_protocol_adapter.py` connects generated structures to semantic builders and parsers.  Handwritten protocol code is limited to semantic transforms, checksums, and transport framing.
- `coordinator*.py` owns connection lifecycle, queries, notifications, state, verification, and diagnostics.
- `light.py`, `light_services.py`, and the model profile expose only capabilities declared for the configured device.
- Effect Studio uses the same model profiles, capability contracts, and exact-SKU catalogues rather than a separate model architecture.
- `scenes.py` loads committed exact-SKU Govee snapshots.  Catalogue data and BLE transport evidence remain separate.

Every exact SKU has its own profile, support quality, catalogue identity, and product capability data.  Compatible models may share a Kaitai wire adapter, but do not share whole profiles or exact-SKU metadata.

### Reusing device protocol support

- Declare `command_grammar` and `status_grammar` explicitly, even when they select the same grammar. Basic commands, outgoing basic status queries, command echoes, and optimistic command expectations use `command_grammar`; incoming status frames and their semantic interpretation use `status_grammar`. Missing or unknown grammar keys fail closed, without falling back to another direction or exact model.
- Any declared read domain requires `status_grammar`; power, brightness, colour mode, mode, firmware, hardware, and segment reads also require `command_grammar`. The selected complete status root must cover every declared read domain, proven by an exact-profile integration test. Do not add fallback or per-domain status routing, or a Python grammar-metadata registry.
- Declare `effect_grammar` independently of basic command and status compatibility. It selects A3 and Workshop codecs, including their canonical semantics; it does not authorize effect application, catalogue reuse, activation, or readback policy. Workshop application also requires the exact-model capability contract and an implemented activation route.
- Declare video modes and setting capabilities on the exact-model profile. `video_grammar` selects compatible mode, query, writer, readback, and command-ACK semantics independently of the basic grammars; it does not authorize a model or imply support for every companion setting. Grammar keys select codecs directly, not another model's profile.
- Declare each model's `music_modes` explicitly. The shared slug-to-wire-ID registry records encoding knowledge, not product support.
- Pass the effective device profile to semantic segment builders. Construct and validate the entire request before cancelling previews, acquiring user control, changing optimistic state, or writing to BLE. Whole-device masks remain separate from individually selectable segments.
- Reuse `govee_segment_page` in status KSY with the evidenced segment count, page size, and unused-byte rule. Its fixed page body has four wire slots; only the declared meaningful records contribute to observed state. Keep profile counts consistent with the selected schema, and preserve uncertain unused bytes rather than treating zero-valued records as absent.

Extension tests should demonstrate reuse through declarations without unrelated exact-model codec allowlist edits. Register a test-only exact-model profile and an independent status-root key rather than replacing an existing root or mocking profile lookup. Synthetic profiles and speculative fixtures establish these software boundaries, not physical device compatibility; the H66A0 fixture does not enable real H66A0 runtime support.

Partial fixtures must declare only the minimal capabilities and read domains they exercise, rather than inherit a full device's contract.

### Outbound transmission

All outgoing BLE packets pass through `GoveeBLECoordinator._async_write_packet`.
Callers retain connection, locking, priority, retry, transaction ordering, progress, and idle-lease policy.
The shared writer must not reconnect or acquire locks: connection setup itself sends identity queries through it.

An exact-model profile may declare a synchronous, stateless `outbound_transform` from logical packet bytes to non-empty wire bytes.
The default sends the logical packet unchanged.  Transforms reject invalid input with `ValueError`; rejection never falls back to plaintext.
Each physical attempt transforms the original logical packet, including retries.
Command expectations are derived from logical bytes after successful transformation and before writing; queries do not arm command expectations.
Diagnostics record the actual wire bytes only after a successful write.  A successful write does not prove device state or effect activation.
This hook does not establish encrypted-device support or replace Kaitai ownership of wire structures.

## Planning support for a new model

Use the same short structure for human and agent plans:

1. **Request and known context**
2. **Research findings**
3. **Candidate support scope**
4. **Model-specific changes and owner checks**

Research the exact device through available app behaviour, public sources, related projects, and supplied material.  Review contributed protocol files rather than accepting them as authoritative.  Aim for broad in-scope support, include defensible hypotheses as clearly speculative Kaitai, and preserve unknowns instead of inventing facts.

The plan should describe only model-specific findings and work.  Link to this document instead of repeating repository architecture, protocol, support, release, or validation rules.

## Support lifecycle

| Status | Meaning |
| --- | --- |
| Experimental | Prerelease-only exact-model implementation awaiting owner qualification. |
| Partial | Stable owner-confirmed support with known gaps that remain intentionally unavailable. |
| Compatible | Stable owner-confirmed support with no known compatibility issue in the exposed feature set, but incomplete model documentation. |
| Supported | Fully documented support where every known feature is implemented or explicitly excluded and every enabled wire path has evidence-backed repository Kaitai coverage. |

The progression is:

1. A device owner requests an exact model and volunteers to test.
2. A maintainer researches the complete known device surface and builds the broadest candidate that can be modelled without fabricating protocol facts.
3. An immutable exact-SHA prerelease is published with a model suffix such as `.h617p`.
4. The owner tries the available features and reports failures with redacted diagnostics.
5. Failed capabilities are fixed or removed.
6. The model moves to Partial or Compatible before stable merge.
7. Supported is a later promotion after the model's features and explicit exclusions are completely documented.

An Experimental profile that receives no owner confirmation is not merged as stable support.
Prerelease versions are stamped only in the packaged artifact; feature branches retain the current stable source version so release-candidate metadata cannot leak into master.

## Device-owner validation

The first prerelease request should stay short: provide the release link, explain installation or reconfiguration, ask the owner to try the available features, and request redacted diagnostics immediately after anything fails.  Include the privacy warning above.

Use a targeted follow-up checklist only when a result needs clarification.  Ask for the action, expected and observed result, Home Assistant state, restoration result, exact prerelease, and immediate diagnostics.  Device owners are not expected to build the repository or run its developer test suite.

If the config entry never loads, enable debug logging for
`custom_components.ha_govee_led_ble` and copy only the address-free protocol
rejection lines.  Do not attach a complete unredacted Home Assistant log.

## Protocol evidence and speculative schemas

Model numbers, catalogue grouping, and related-model behaviour are clues, not
compatibility proof.  A related model may share power commands while using
different colour, segment, scene, or readback structures.

Enable each capability independently.  Document failures as well as successes so known gaps remain unexposed.

The repository has two protocol evidence classes:

- `tools/ble/kaitai/*.ksy` contains evidence-backed H617A, H6199, and independently verified shared structures.
- `tools/ble/kaitai/speculative/*.ksy` contains exact-model hypotheses for Experimental, Partial, and Compatible work.

When no official-app BLE capture is available, model the full known exact-model surface as far as the available evidence permits.  Every enabled wire path must use exact-model speculative KSY or a genuinely compatible evidence-backed root.

Every speculative KSY must begin its top-level `doc` with `SPECULATIVE`, name
the exact model and support issue, state the compatibility hypothesis, and list
unresolved assumptions.  Preserve uncertain bytes as opaque or unknown data.
Do not invent enum members, semantic names, `reserved` fields, or `valid`
constraints.

Speculative roots may be generated into an exact-model prerelease package, but
only explicitly selected roots belong in the runtime root list.  Their presence
is not protocol proof and does not justify enabling untested capabilities.

Promoting a schema to the evidence-backed parent directory requires attributable
official-app captures, representative direct-byte parser tests, successful
owner qualification, and explicit documentation of every enabled path.  Follow
the public [`ios-ble-capture` methodology](https://github.com/teh-hippo/ios-ble-capture/blob/main/docs/methodology.md).

Diagnostics retain bounded raw transmit and receive frames, including parser
rejections.  Raw hex is the replay input: after correcting a KSY, add the
relevant frame directly to `tests/test_kaitai_protocol.py`.  Do not commit
packet captures, diagnostics exports, or a second protocol representation.

Do not add offsets, command literals, or packet enums to entity or coordinator code.

## Exact-SKU scene catalogues

Scene catalogues come from Govee's exact-SKU catalogue endpoint through the existing repository tool:

```bash
make protocol
uv run python tools/ble/refresh_scene_catalogues.py H6179
```

Commit the full generated snapshot.  Do not copy another model's catalogue or
hand-select a subset.  Catalogue availability proves scene identity and vendor
payload data only; it does not prove transport, activation, upload, or readback
compatibility.

A committed snapshot may remain available as inert metadata while the model
profile keeps scene controls disabled.  An Experimental candidate may expose
scene activation when an exact-model transport hypothesis is represented in
Kaitai.  Owner-confirmed visible behaviour and restoration are required before
promotion.

## Repository non-goals

The repository may retain Kaitai schemas and protocol findings for excluded runtime features.  It does not expose:

- Wi-Fi provisioning, cloud control, or account and network setup;
- user-facing on-device timers or schedules;
- host microphone capture or audio-derived control;
- continuous host-driven BLE streaming for real-time audio or animation;
- firmware or OTA updates;
- manufacturer-style animated scene previews; or
- camera calibration that depends on Govee Wi-Fi or cloud services.

Onboard device-microphone modes, ordinary BLE commands, and bounded multipart effect uploads remain in scope.

## Validation

Before considering a contribution complete, run `make check` on the final tree and resolve any failures.  Run `make package` only when producing a distributable package.  Hassfest and HACS remain CI-enforced checks.

Keep Conventional Commit merge parsing enabled in semantic-release so release-bearing merges still trigger releases when the branch commits are fixups.

For live qualification, distinguish optimistic entity state from fresh BLE readback.
Use `homeassistant.update_entity` when verifying state outside the command's confirmation queries.
H617A static RGB is confirmed through complete segment replies, not the colour-mode reply.

### Maintainer release-candidate qualification

Use a published RC installed through HACS for live qualification, not SSH deployment or direct file copying.
When release and live testing are authorised, follow this established route without asking the owner to choose a deployment mechanism again.

1. Run the final `make check`, commit the reviewed candidate, and push its feature branch.
   Use the [prerelease workflow](.github/workflows/prerelease.yml) with that branch selected, its exact full commit SHA as `target_sha`,
   a fresh `version` in `MAJOR.MINOR.PATCH-rc.N.SUFFIX` form, and `publish=true`.
   Review release notes before publishing.  The workflow stamps the packaged manifest; do not bump source versions for the RC.
   Require a successful run and verify the tag's target SHA and the package checksum.
2. Before deployment, capture the installed release and the test devices' restorable state, including hidden mode/settings when a light is off.
   If a state cannot be safely restored, resolve that before changing it.
3. Discover the integration's HACS `update` entity through Home Assistant.
   Refresh it with `homeassistant.update_entity`, then call `update.install` with the exact RC tag as `version`; do not rely on `latest_version`.
   Confirm the installed tag, then restart Home Assistant with `homeassistant.restart` to load the new Python code.
4. Wait for Home Assistant and the target config entries to load, then confirm the runtime manifest version in diagnostics matches the RC.
   HACS installation metadata alone proves downloaded files, not running code.
   Exercise the affected workflows through the normal REST/WebSocket interfaces and require fresh BLE readback rather than optimistic entity state.
5. Clean up temporary previews and restore each device's captured state even if a test fails, then verify restoration through fresh readback.
   Keep diagnostics private and bounded.  Report the exact RC, observed results and any unverified behaviour.
   Publish another exact-SHA RC for subsequent source fixes rather than hotpatching the installation or reusing a tag.
