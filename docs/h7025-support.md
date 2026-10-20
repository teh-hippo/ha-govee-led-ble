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
reporter's eight-byte snapshot threshold.  The candidate follows that app
writer and the existing shared fragmenter.  This difference needs owner
qualification, not a global transport change.

An offline six-colour Hopping comparison separates body length from framing:

| Construction | Stream bytes | A3 packet indices | Decoded content |
| --- | --- | --- | --- |
| App-derived candidate | 27, including two trailing body zeros | `00`, `ff` | Six RGB colours, background RGB, brightness, two zero tail bytes |
| Reconstruction of the published rule | 25 before frame padding | `00`, `01`, empty `ff` | Same palette and tail fields; frame padding supplies the zeros |

Using the full 27-byte stream with the published rule still produces three packets.
The reporter sequence here is reconstructed, not a supplied capture.  Matching
decoded content does not establish that their firmware accepts both framings.

The app uses `33 05 13 03` for Rhythm.  The reported `33 05 00` shortcut is not
emitted.  Its amber result remains a device observation; the occurrence of
amber bytes in `AA 12` does not establish a cause.  The inspected status path
treats that register as wake-up configuration.

## Candidate support scope

Whole-string power, percent brightness, RGB and 2700..6500 K colour temperature
use the shared basic command codec.  Kelvin writes use H7025's direct white
RGB field, not H617A's black value.  An independent H7025 status root reads
power, brightness, mode and identity.  The fifteen-bulb whole-device mask does
not enable individual segment controls or claim a physical IC count.

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

Scenes, DIY, individual segments, phone microphone, LAN/cloud operations and
on-device schedules are outside this candidate.  See the
[contributor guidance](../CONTRIBUTING.md) for evidence and release handling.

## Model-specific changes and owner checks

The exact-model profile and catalogue select `h7025_music_write`,
`h7025_music_body` and `h7025_status_reply`.  Shared acknowledgement and
transport handling remain unchanged.  Enum-backed direction edits use the
same parameter preparation and retained-body path as other music settings.

The offered contributor `.ksy` has not yet been submitted.  Compare it against
these schemas and the original ordered snapshot bytes when available; retain
differences explicitly rather than treating either interpretation as firmware
proof.

Add H7025 manually when trying the candidate; automatic discovery is not enabled.
The owner trial should use an exact-SHA H7025 prerelease and cover basic light
controls, entering and leaving Rhythm, each palette-backed mode, and changing
palettes and exposed parameters.  Include a six-colour Hopping case to
exercise the disputed final-fragment boundary.  After a failure, stop rather
than repeatedly sending the same sequence and collect immediate redacted
diagnostics, app/device versions and the observed result.  Do not attach
addresses, serial numbers, account details or complete logs.

No H7025 BLE playback, readback or restoration has yet been qualified.
