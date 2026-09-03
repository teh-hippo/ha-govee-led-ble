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

## Support lifecycle

| Status | Meaning |
| --- | --- |
| Experimental | Prerelease-only candidate for an exact model, with a named device owner testing a limited capability set. |
| Partial | Stable owner-confirmed support with known gaps that remain intentionally unavailable. |
| Compatible | Stable owner-confirmed support with no known compatibility issue in the exposed feature set, but incomplete model documentation. |
| Supported | Fully documented support where every known feature is implemented or explicitly excluded and every enabled wire path has evidence-backed repository Kaitai coverage. |

The progression is:

1. A device owner requests an exact model and volunteers to test.
2. A maintainer researches the model and enables only a conservative candidate feature set on a feature branch.
3. An immutable exact-SHA prerelease is published with a model suffix such as `.h617p`.
4. The owner reports each exposed control as working or failing and attaches redacted diagnostics.
5. Failed capabilities are fixed or removed.
6. The model moves to Partial or Compatible before stable merge.
7. Supported is a later promotion after the model's features and explicit exclusions are completely documented.

An Experimental profile that receives no owner confirmation is not merged as stable support.
Prerelease versions are stamped only in the packaged artifact; feature branches retain the current stable source version so release-candidate metadata cannot leak into master.

## Useful device-owner validation

Test each exposed capability independently and report the visible result:

- setup and restart;
- power;
- several brightness levels;
- RGB colours;
- colour-temperature minimum, midpoint, and maximum;
- state refresh;
- idle disconnect and reconnect;
- handoff from the Govee app back to Home Assistant; and
- restoration of the original device state.

Export integration diagnostics after the relevant phase.  Device owners are not expected to build the repository or run its developer test suite.

For each tested action, report:

1. the exact prerelease version and commit SHA;
2. the action and expected visible result;
3. the observed result;
4. whether Home Assistant state readback matched;
5. whether the original device state was restored; and
6. diagnostics exported immediately after the action.

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

When no official-app BLE capture is available, a contribution must still add either:

- the minimum exact-model speculative KSY roots needed by the candidate; or
- an explicit speculative compatibility alias when an evidence-backed root is reused byte-for-byte.

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

A committed snapshot may remain inert until the model profile enables scenes
and `SCENE_ENTRIES` loads it.  Scene support additionally requires Kaitai
coverage for the relevant wire paths, representative parameter parsing,
owner-confirmed visible behaviour, and restoration testing.
