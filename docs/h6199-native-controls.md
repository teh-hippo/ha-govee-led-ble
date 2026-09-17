# H6199 Native Controls (#294)

The additional DIY selector, Gradient, strip direction, camera position and
camera status layouts use `speculative/h6199_control_payload.ksy`. Existing
H6199 roots import them without promoting their evidence class. APK analysis
and direct register tests are not official-app BLE captures.

Direct register acceptance/readback/restoration was tested on H6199 main
HW3.02.01/FW1.10.04, Wi-Fi HW1.03.00/FW1.00.33, Pact2/1. The runtime
`h6199_camera_controls_state(model, identity)` qualification applies to these
four independently addressed registers. Unknown identity is not permission. Older revisions
still need owner qualification. No new DreamView or upload route is enabled.

| Field | Treatment | Qualification Remaining |
| --- | --- | --- |
| DIY0a/code | Schema and direct-byte parser coverage only; no production selector builder | A selected code does not prove populated content or playback; no new uploads or automatic DIY recovery authorization |
| A3 Gradient | Native off/on select, readback verified after writes | Actual UI is Color > Subsection > Gradient; visual meaning unqualified, not HA transition duration |
| Static detail Gradient | Observed; unknown tail retained by generated parser | No Kelvin or RGB semantics inferred from trailing zeroes |
| Direction30 | Disabled-by-default config select, 0 clockwise / 1 anticlockwise | Visual orientation and other revisions |
| Camera position31 | Disabled-by-default config select, 0 top / 1 bottom | Visual orientation and other revisions |
| Camera status32 | Diagnostic only; 1 connected directly tested | 0 absent / 2 incompatible APK-only, other bytes and timeout unknown |
| ACK | Generated parser records success response | ACK never substitutes for fresh register readback |

Gradient also defaults disabled to keep these newly qualified controls opt-in.
Independent register writes do not enter static/video mode, turn on the light,
or write sibling registers. They do not participate in effect recovery because
effect application does not author these registers. State is never restored
from HA storage as observed readback. A pending/missed camera query clears old
status to unknown and cannot disable the basic light.

Runnable coverage is in `tests/test_h6199_native_controls.py`. Software fault
injection and generated parser checks are not physical qualification. A future
published exact-SHA RC still needs owner-visible orientation/Gradient testing,
ordinary HA control and independent fresh device readbacks plus restoration.
