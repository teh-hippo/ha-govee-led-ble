# H6102 application candidate — issue #115

Owner baseline: firmware **3.02.02**, working power/brightness/RGB in RC4.
Scenes and Effect Studio parity with the H617A 7.5.2 workflow remain owner acceptance targets.
This implementation is Experimental; synthetic tests establish software behavior, not physical qualification.

## Evidence and independently resolved features

Sources below are relative to the Android 7.6.01 `full/sources/com/govee/` extraction.

| Surface | Evidence / candidate | Remaining qualification |
| --- | --- | --- |
| Pact | `dreamcolorlightv1/pact/Support.addSupportPact` registers goods 18 with 1/1, 1/2, 10/1 and 10/2; `supportV1UIV3` and `LightVersionServiceImpl.getDiySupport` select the modern route for Pact 10 | Automatic advertisement evidence or explicitly owner-qualified Pact; firmware never selects Pact |
| Power, brightness, identity | Shared switch/brightness/firmware/hardware controllers, exact H6102 status root | Bootstrap subscribes and reads even without Pact; no mode/effect writes under unknown context |
| RGB, logical segments | Modern RGBIC shared static command, fifteen logical segments, five three-record A5 pages | Physical mapping; logical count does not establish physical IC count |
| Kelvin | `rgbiclight/mode/color/ColorControllerConfig`, `dreamcolorlightv1/ble/SubModeColorV2`, common `KelvinConfig` 2000–9000 range | RGB-rendered white, not a separate white emitter; retained Kelvin is not fresh measured Kelvin |
| Scenes | Complete committed H6102 snapshot: 240 entries; shared modern scene upload/selector grammar | Visible activation and restoration on owner device |
| Single / Mixed | `rgbiclight/newdiy/NewConfigManager`: Fade 0:(0,1,2), Jump 1:(0,2), Blink 2:(0,1,2), Marquee 3:(3,4,5), Stream/Flow 8/9:(9,10), Chase 10:0, Music 4:(8,6,7); palettes 1–8 except Chase 1–3; Single rate 1–100, Mixed speed 0–100 with up to four components from 0,1,2,3,8,9 | Visible timing/direction and restoration |
| Painted | Actual AcNewDetail route uses A3/03 physical-IC coordinates, independent of fifteen logical zones | Unknown physical count blocks coordinate authoring; source topology is retained rather than reconstructed from highest index |
| Advanced | `DiyApplyVM.e0 -> DiyStudio.e`, A3/02 and exact-profile selector **402** | Owner-visible edits; no catalogue carrier substitution or Workshop 401 |
| Native DIY | `DiyM` selectors 501–507, subtype 02; `ScenesOp.changeEffectStr4Sku` transforms 504/506 with H6102 preset count 60, yielding quantities 12/30 | Preset constants do not establish runtime geometry; nongeometry edits remain available, geometry edits require known IC count |
| Native music | `rgbiclight/mode/music/MusicMode`: basic 5/3/4/6 always present for modern Pact; new seven require BK 2.01.xx + FW ≥2.04.00 or FRK 3.xx.xx excluding 3.04.xx + FW ≥3.01.00 | Qualified shared named tails; Bloom/Shiny independent of geometry, other fresh bodies require IC count. Retained-body nongeometry edits preserve companions. No upload for basic four |
| ACK / activation | DIY upload result at absolute byte 2, music A3/41 at byte 3; zero success; upload before selector | ACK proves transport acceptance only; fresh mode/selector reply still required |
| Gradual | Shared boolean switch, Pact 10; 33 A3 write / AA A3 query | Owner-visible toggle and restoration qualification |
| Limit | Shared boolean switch, Pact 10 and HW ≥1.00.02; 33 0E write / AA 0E query | Meaning and visible behavior remain owner qualification |
| Pact 1 | Extended static command independently enabled at HW ≥1.00.03 and FW ≥1.06.00 | A1 DIY and legacy RGB remain unavailable; static authorization never grants the whole multi opcode |

The 1.03.01 firmware boundary in `OldDreamColorUtil` is an app migration condition, not wire authorization.
Phone microphone injection, timers, OTA, provisioning and continuous streaming remain repository non-goals.

## Runtime and verification

The exact profile registry, advertisement parser, profile-generation invalidation, shared physical writer,
compiler, preview admission, saved library and deployment engine are reused. Observed Pact overrides
configured context. Reconnection invalidates identity-dependent grants before awaiting connection setup.
Every effect sequence checks profile generation, and physical music selectors check the effective roster.

`tests/test_h6102_capabilities.py` covers two independent devices, roster thresholds, unknown context,
catalogue bounds, reconnect revocation, pre-write rejection and real-coordinator saved Apply with matching
and contradictory fresh status. Confirmed Apply means **activation match**, not effect-body readback.
Uploaded bodies and optimistic state are never promoted to observed content. Owner BLE captures and
visible scene/Studio/restoration results are still required.
