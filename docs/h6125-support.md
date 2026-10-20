# H6125 candidate support

## Request and known context

[Issue #117](https://github.com/teh-hippo/ha-govee-led-ble/issues/117#issuecomment-6176612974)
reports hardware **3.01.10**, firmware **3.04.37** and pact **10/2**.
That controller uses the modern FRK route, not the pact-1 register and music encoding.
Its earlier power-only presentation was an integration restriction, not evidence that the strip lacked RGB.

H6125 remains **Experimental**.  Application behaviour and public device reports establish candidate compatibility,
not physical qualification of every controller generation.
The [manufacturer manual](https://m.media-amazon.com/images/I/91uas4N3quL.pdf) describes a 5 m, 12 V RGBIC strip
with Bluetooth, app/control-box operation and microphone music synchronisation.
It does not specify a hardware-revision protocol matrix.

## Research findings

Pact, firmware and hardware are evaluated together.  Firmware alone never selects the controller family.
Colour, segment, scene and music capabilities have independent thresholds.

| Controller route | Colour and segment readback | Music selector |
| --- | --- | --- |
| Original Telink, firmware below 1.03.01 | `0x0b` RGB; four RGB-only A2 pages | `0x0c`, four modes |
| Intermediate pact 1 | `0x0b` RGB; four RGB-only A2 pages | `0x11` |
| Pact 1, HW 1.00.03+ and FW 1.06.00+ | `0x15` RGB/Kelvin; five brightness/RGB A5 pages | `0x11` |
| BK hardware 2.01.xx, pact 10/1 or 10/2 | Modern RGB/Kelvin and A5 pages | `0x13` |
| FRK hardware 3.xx.xx, pact 10/1 or 10/2 | Modern RGB/Kelvin and A5 pages | `0x13` |

The separate hardware family 3.04.xx is not admitted as FRK.
Unknown, malformed or contradictory identity remains limited to power and identity.
Pact 10/3 is not treated as an alias for 10/2.

The four basic music modes remain available below expanded-music thresholds.
The eleven-mode roster requires firmware 1.07.00+ on pact 1, 2.04.00+ on BK, or 3.01.00+ on FRK.
The reporter's exact identity therefore qualifies for the modern eleven-mode candidate.

Pact 10 uses percentage brightness without register scaling.
The original Telink route uses 6-254.  The DreamColor pact-1 route retains 6-254 below hardware 1.00.04
and 20-254 from that revision.
[An identified older report](https://github.com/homebridge-plugins/homebridge-govee/issues/93)
records hardware 1.00.04, firmware 1.07.01, pact 1/1 and fifty ICs.
Minimum-register evidence differs between some application paths; the candidate preserves the existing DreamColor mapping
rather than guessing a scale from an ambiguous read value.  Owner brightness/readback checks remain important.

### Geometry and catalogues

The exact-product configuration declares **50 physical ICs** and **15 logical segments** for stock H6125.
These are different coordinate systems.  Fifty is declared product metadata, not a fresh measurement,
and must not be inferred from the number of A2/A5 records.
Geometry-dependent requests are bounded to their declared coordinate system.

The committed vendor scene snapshot retains all 240 entries and their original identities.
Original controllers expose ten known selector-only scenes.
The intermediate selector-only route exposes 64, including the legacy Work selector absent from the current snapshot.
That local entry uses the reserved local catalogue namespace and is hidden from other revisions.
Uploaded-scene routes expose the 240 vendor entries; unsupported selectors are rejected before control side effects.

## Candidate support scope

Matched revision profiles provide power, brightness, RGB, logical segment colours and native microphone modes.
Extended colour profiles add whole-strip and segment Kelvin, segment brightness and painting where the route permits it.
Kelvin describes RGB-rendered white, not a claim of separate white emitters or measured colour-temperature accuracy.

The effect surface is selected per device:

- Basic and mixed DIY use A1 command 02 on pact 1 and A3 subtype 04 on pact 10.
- Painting uses the physical-IC A3 route, independently of the Type04 carrier.
- Named DIY templates use their own selectors 501-507 and H6125 preset quantities, not another model's quantities.
- Advanced and shared Workshop content use their independently authorised A3 routes and selectors.
- Legacy profiles do not inherit newer templates, editing controls or workflow permissions.

Uploads requiring acknowledgement wait for a matching protocol and command before activation.
A1 and A3 replies with the same command number are not interchangeable.
The protocol has no verified transaction identifier, so a delayed same-command reply within a later attempt remains ambiguous.
An ACK proves neither effect rendering nor applied state; fresh mode/selector readback is still required.

Saved effects, previews, direct controls and catalogue responses use the same effective profile.
Cached capabilities stay stable across reconnects, while identity-dependent authorisation is revoked until fresh replies arrive.
A changed profile or transport invalidates prepared work before it is sent.

RGB-only A2 pages never fabricate segment brightness.
Recovery can retain and restore a colour-only layout without inventing brightness values.
Stored or restored state is not promoted to a fresh observation.

Timers, provisioning, cloud control, phone audio injection, continuous streaming and OTA remain
[repository non-goals](../CONTRIBUTING.md#repository-non-goals).
H6125 does not inherit another product's Limit, camera or video controls.

## Model-specific changes and owner checks

The exact-SKU profile and catalogue own permissions and product metadata.
The selected H6125 Kaitai roots own the register, selector, page and ACK layouts.
Shared adapters, transaction handling, recovery, light services and Studio consume those declarations.

Relevant software coverage is in `tests/test_h6125_capabilities.py`, `tests/test_const.py`,
`tests/test_coordinator.py`, `tests/test_upload_ack.py`, and the shared scene, effect and frontend suites.
These checks establish software behaviour, not physical compatibility.

Use a published `.h6125` prerelease through HACS with beta versions enabled, then restart Home Assistant.
Try the available controls and effects and report what works or fails.
For a failure, export diagnostics immediately afterwards and remove Bluetooth addresses, serial numbers and unique BLE-name suffixes.

Follow-up qualification should cover brightness at several levels, RGB/Kelvin, first/middle/last logical segments,
native scenes, music parameters, each available Studio workflow, BLE handoff and restoration of the original state.
Begin with the reported FRK identity, then qualify the other mapped generations independently.
Do not close the issue or promote support quality merely because packet encoding, an upload ACK or another model's tests succeeded.
