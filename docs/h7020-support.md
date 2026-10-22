# H7020 support

## Request and known context

H7020 is an outdoor RGBIC string light with fifteen bulbs per string.  Its [manufacturer installation instructions](https://www.manualslib.com/manual/3497552/Govee-H7020.html?page=4#manual) permit joining at most two strings.  Follow those instructions for compatible connections, the adapter and waterproofing; this integration does not establish mixed-model compatibility.

The owner of [#363](https://github.com/teh-hippo/ha-govee-led-ble/pull/363) confirmed the original power, percentage brightness, RGB and white controls through an ESPHome Bluetooth proxy on Pact 1/code 1.  Firmware and hardware versions were not recorded.  H7020 is **Supported**; its expanded APK-derived controls and speculative schemas still await physical confirmation per capability.  Installation and schema-promotion rules follow [CONTRIBUTING.md](../CONTRIBUTING.md).

## Research findings

| Surface | Evidence | Disposition |
| --- | --- | --- |
| Identity | Exact-model candidate covers Pact 1/code 1 and Pact 2/code 1 | Other or unknown Pact values retain power, brightness and identity reads only |
| Brightness | Owner-confirmed percentage register | No 0-254 scaling |
| Configured strings | One or two strings, fifteen logical bulb positions each | Explicit configuration, not physical attachment detection |
| RGB and white | Candidate colour writes use a four-byte selection mask; Kelvin uses white direct RGB and a discrete companion-colour table | Whole-device and selected-bulb control; candidate range 2000-9000 K |
| Bulb readback | Three brightness/RGB records per page | Five or ten complete pages according to confirmed configuration |
| Scenes | Full exact-SKU catalogue: 51 effects, including 47 uploaded layered bodies | Catalogue identity does not prove physical activation; 40 entries carry speed metadata |
| Music | Rhythm, Spectrum, Energetic and Rolling | Sensitivity and automatic/fixed colour; Rhythm has an authored Dynamic/Soft response |
| DIY | Basic and mixed effects share one upload family; three layered templates use another | Both families activate a separately selected DIY slot |
| Native setting | Power-off memory | Explicit switch with fresh readback |

Exact-model wire differences live in `tools/ble/kaitai/speculative/h7020_*.ksy`.  The implementation reuses shared record, effect-body and acknowledgement structures where their semantics match.  These schemas and synthetic tests are not official-app captures or owner qualification.

The [manufacturer specifications](https://www.manualslib.com/manual/3497552/Govee-H7020.html?page=5#manual) describe RGB and warm white, not a measured adjustable white range.  The candidate's Kelvin range and companion encoding still require visual owner checks.  Between table entries the companion is zero; values are not interpolated.  The earlier black-direct-RGB implementation was internally consistent and reportedly worked, so changing its encoding is not proof that it physically failed.

## Candidate support scope

The candidate includes power, percentage brightness, configured fifteen/thirty-bulb layouts, whole-device and selected-bulb RGB/Kelvin/brightness, native scenes and speed, four onboard music modes, basic/mixed DIY, three layered DIY templates, and power-off memory.

Use **Configured bulb strings** to match the installed one- or two-string setup.  The integration never changes this setting automatically.  It requires acknowledgement followed by matching fresh readback.  Cached configuration can remain visible while unavailable, but cannot authorise a bulb-mask write.

The integration refreshes configuration before each mask-dependent transaction and discards stale geometry-dependent state when the count changes.  Owning BLE does not prevent the official app from changing configuration through another connection.  This preflight is not an atomic device-side lock.

Effect Studio uses the shared exact-model catalogue, authoring and deployment paths.  DIY requires an explicitly approved disposable slot; the integration cannot discover an unused slot from its selector.  A failed upload must not activate incomplete content.

Readback reports selectors, not uploaded bodies or scene speed.  Rhythm response is retained authored state, not a fresh device observation.  A single Kelvin value and per-bulb RGB do not uniquely recover mixed RGB/white intent.  Previews refuse this ambiguous static state, and automatic rollback does not repaint it or claim lossless restoration.  A previously off light still receives independent power-off cleanup after failure.  Ordinary direct control does not require preview restorability.

Painted effects, unrestricted advanced/Workshop authoring and custom-music authoring are not exposed.  Cloud control, Wi-Fi setup, timers, firmware updates and phone-microphone streaming remain [repository non-goals](scope-policy.md).

## Model-specific changes and owner checks

The exact profile selects H7020 command/status roots and independently compatible shared effect-body codecs.  Geometry, controls, observations and recovery use the common coordinator and entity paths.

Install the model-specific prerelease through HACS and restart Home Assistant.  Check the available controls on the actual one- or two-string installation.  In particular, qualify Kelvin appearance, complete bulb state, both DIY upload families and explicit configuration changes.  Changing the app's configuration while BLE remains connected is a separate concurrency check, not an assumed capability.

After a failure, record the action and observed result, then obtain integration diagnostics immediately.  Include firmware/hardware versions and the exact prerelease, and remove Bluetooth addresses, serial numbers, account details and other unique identifiers before posting.
