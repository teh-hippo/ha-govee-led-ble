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

- `custom_components/ha_govee_led_ble/const.py` owns the exact-model `ModelProfile` registry.  Profiles declare product capabilities and runtime policy; `wire_model` may reuse another model's protocol only where the bytes are compatible.
- `tools/ble/kaitai/**/*.ksy` is the only BLE wire-structure source.  Generated modules under `generated_protocol/` are build outputs and are never edited manually.
- `generated_protocol_adapter.py` connects generated structures to semantic builders and parsers.  Handwritten protocol code is limited to semantic transforms, checksums, and transport framing.
- `coordinator*.py` owns connection lifecycle, queries, notifications, state, verification, and diagnostics.
- `light.py`, `light_services.py`, and the model profile expose only capabilities declared for the configured device.
- Effect Studio uses the same model profiles, capability contracts, and exact-SKU catalogues rather than a separate model architecture.
- `scenes.py` loads committed exact-SKU Govee snapshots.  Catalogue data and BLE transport evidence remain separate.

Every exact SKU has its own profile, support quality, catalogue identity, and product capability data.  Compatible models may share a Kaitai wire adapter, but do not share whole profiles or exact-SKU metadata.

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
