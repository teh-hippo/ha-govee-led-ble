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
| Supported | Fully documented support where every known feature is implemented or explicitly excluded and enabled wire behaviour meets the repository evidence standard. |

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

## Evidence and protocol changes

Model numbers and APK grouping are clues, not compatibility proof.  A related model may share power commands while using different colour, segment, scene, or readback structures.

Enable each capability independently.  Document failures as well as successes so known gaps remain unexposed.

Novel wire structures require attributable official-app captures and updates to the repository-owned Kaitai schemas.  Follow the public [`ios-ble-capture` methodology](https://github.com/teh-hippo/ios-ble-capture/blob/main/docs/methodology.md).  Do not add offsets, command literals, or packet enums to entity or coordinator code.
