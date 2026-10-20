# H7025 candidate support

## Request and known context

[#148](https://github.com/teh-hippo/ha-govee-led-ble/issues/148) reports working
H7025 music snapshots and failures when a style receives another style's tail.
The maintainer authorised building a candidate from the report and available
app behaviour without waiting for additional captures.  H7025 remains
Experimental.  This is not H607C support or a LAN transport implementation.

## Research findings

The H7025 path in Android 7.6.01 corroborates the reported music IDs and most
tail fields.  Shared serializers do not select the product's ID: the H7025
caller explicitly selects Hopping `48`, independently of the producer's own
default.  Hardware, firmware and app revisions associated with the report
remain unknown.

| Mode | ID | Body after the RGB palette | Candidate authoring |
| --- | --- | --- | --- |
| Rhythm | `03` | No A3 body; settings are inline in the selector | Sensitivity, Dynamic/Calm, optional single fixed colour |
| Sway | `8e` | Three zero bytes in the app's output | 1..8 colours |
| Flow | `59` | Direction, group count, ICs per group | 1..8 colours, clockwise/counterclockwise, 1..3 groups |
| Star | `98` | Background RGB and a final byte named distance | 1..8 colours and background; final byte preserved |
| Twinkle | `8f` | Three zero bytes in the app's output | 1..8 colours |
| Hopping | `48` | Background RGB, brightness, two zero bytes | 1..8 colours, background and brightness 1..50 |
| Rolling | `5a` | Direction and two zero bytes | 1..8 colours, left/right/spread |
| Day and Night | `37` | Piece count, speed, gradient | 1..8 colours and 1..3 pieces |
| Piano Keys | `34` | Gradient, key count, speed, minimum/maximum off count | 1..5 colours; reported `00 05 0a 04 04` preset retained |
| Separation | `5d` | Direction and two zero bytes | 2..8 colours, left/right/spread/gather |

Sensitivity is 0..99 for each mode.  The no-colour sentinel is RGB `01 01 01`,
not black.  The Piano preset does not establish physical IC geometry; this
candidate does not derive new key bounds or companion values from bulb count.

The app's BLE writer permits 17 bytes in the final fragment, unlike the
reporter's original eight-byte snapshot threshold.  The candidate follows
that app writer and the existing shared fragmenter.

An offline six-colour Hopping comparison separates body length from framing:

| Construction | Stream bytes | A3 packet indices | Decoded content |
| --- | --- | --- | --- |
| App-derived candidate | 27, including two trailing body zeros | `00`, `ff` | Six RGB colours, background RGB, brightness, two zero tail bytes |
| Reconstruction of the published rule | 25 before frame padding | `00`, `01`, empty `ff` | Same palette and tail fields; frame padding supplies the zeros |

Using the full 27-byte stream with the published rule still produces three packets.
The reporter sequence in this comparison was reconstructed, not a supplied capture.
In the [21 October follow-up](https://github.com/teh-hippo/ha-govee-led-ble/issues/148#issuecomment-6304970706),
the owner supplied ordered two- and three-fragment sequences and reported
successful six-colour Hopping playback for both over LAN, with no blackout
or lockup.  Their two-fragment sequence carries a ten-byte remainder in
`a3 ff`.  This supports retaining the shared fragmenter unchanged; it does
not qualify the BLE integration, upload acknowledgements, readback or restoration.

The app uses `33 05 13 03` for Rhythm.  The reported `33 05 00` shortcut is not
emitted.  Its amber result remains a device observation; the occurrence of
amber bytes in `AA 12` does not establish a cause.  The inspected status path
treats that register as wake-up configuration.

## Candidate support scope

Whole-string and per-bulb power, percent brightness, RGB and 2700..6500 K
colour temperature use the shared basic command codec over a two-byte fifteen-bulb
mask (`0x7FFF`).  Kelvin writes use H7025's direct white RGB field and discrete
table-derived companion RGB, not H617A's black value.  An independent H7025
status root reads power, brightness, mode, identity and four `AA A5` segment
pages (four brightness/RGB records per page across fifteen positions).  Because
`AA 05` carries one Kelvin value while `AA A5` carries per-bulb RGB, mixed RGB
and per-bulb white intent are ambiguous on readback (`segment_colour_mode_ambiguous`);
previews refuse ambiguous static state and rollback does not claim lossless
per-bulb Kelvin restoration.  The fifteen logical positions do not claim a
physical IC count or configurable string count.

The candidate includes the complete exact-SKU catalogue of 114 native scenes
(four selector-only entries and 110 uploaded layered scenes), including 68
scene-speed controls, plus the fifteen standard `A3 04` basic DIY variations
across six families (`fade`, `jumping`, `blinking`, `marquee`, `flow` and
`stream`, speed 1..100, palette 1..8) and Mixed DIY (speed 0..100, up to four
components) in Effect Studio.  DIY requires an explicitly approved disposable
slot and positive upload acknowledgement (`diy_slot_policy="approved_observed"`,
`diy_requires_upload_ack=True`).

All ten onboard music modes are available through the light's effect selector
and Effect Studio.  Each of the nine palette-backed modes uploads its complete
body before activation and requires a positive upload acknowledgement.
Acknowledgement confirms neither rendering nor resident-body equality.
Sensitivity-only edits retain the existing body, as in the app.
Other retained parameter edits upload the edited body and activate it only
after a positive acknowledgement.  A timeout or disconnect after an upload
attempt aborts without automatically replaying it; pre-upload connection
retries remain available.

Stored bodies, palettes and unknown companion bytes use the shared retention
and recovery path.  They are not fresh readback.  A failed upload invalidates
retained body knowledge; recovery cannot invent a previous palette.

Automatic discovery, configurable string counts (`0x0F`), Painted/graffiti DIY,
the nine bespoke `A3 58` DIY sub-effects, unrestricted Workshop/advanced layer
creation, the three-state `0x41` power-off memory register, phone microphone,
LAN/cloud operations and on-device schedules are outside this candidate.  See
the [contributor guidance](../CONTRIBUTING.md) for evidence and release handling.

## Model-specific changes and owner checks

The exact-model profile and catalogue select `h7025_music_write`,
`h7025_music_body` and `h7025_status_reply`, alongside the exact 114-scene
snapshot and standard `A3 04` DIY families.  Shared acknowledgement and
transport handling remain unchanged.  Enum-backed direction edits use the
same parameter preparation and retained-body path as other music settings.

The offered contributor `.ksy` has not yet been submitted.  Compare it against
these schemas and the original ordered snapshot bytes when available; retain
differences explicitly rather than treating either interpretation as firmware
proof.

Add H7025 manually when trying the candidate; automatic discovery is not enabled.
The owner trial should cover basic and per-bulb light controls, complete four-page
segment readback, representative scenes and speed controls, basic/mixed DIY with an
approved slot, entering and leaving Rhythm, each palette-backed music mode, and
changing palettes and exposed parameters.  After a failure, stop rather
than repeatedly sending the same sequence and collect immediate redacted
diagnostics, app/device versions and the observed result.  Do not attach
addresses, serial numbers, account details or complete logs.

No H7025 BLE playback, readback or restoration has yet been qualified.
