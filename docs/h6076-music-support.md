# H6076 music candidate

## Request and known context

Issue [#343](https://github.com/teh-hippo/ha-govee-led-ble/issues/343) reports the H6076 music selector and companion bodies from two decrypted Android Bluetooth snoop logs of the Govee app, taken on hardware 3.05.00 with software 1.04.05.  That session used the V1 encrypted transport.  The reporter replayed the plaintext frames over the LAN API and offered to test a prerelease over Bluetooth.  An earlier owner report in [#247](https://github.com/teh-hippo/ha-govee-led-ble/issues/247) shows a plaintext H6076 on hardware 3.01.01 with software 1.04.08, so both transports exist in the field.

Music is an unqualified capability of the Partial H6076 profile.  It has explicit maintainer approval for stable inclusion before owner qualification, without changing the model's support label or promoting its speculative protocol evidence.  Physical qualification remains outstanding.

## Research findings

Evidence is the reporter's capture, Android Govee 7.5.30 app behaviour and the reporter's separate LAN integration, [scroom/ha-govee-local-segments](https://github.com/scroom/ha-govee-local-segments).  The capture is reporter-supplied and its raw file has not been reviewed, and no integration or owner Bluetooth test exists yet, so the schemas stay speculative.

| Surface | Evidence | Disposition |
| --- | --- | --- |
| Selector | Capture and app floor-lamp music mode writer: submode `0x0f`, then effect, sensitivity and parameters | `h6076_music_write.ksy`; not the H617A submode `0x13` |
| Effect codes | Capture and app: Energetic 0x00, Hopping 0x02, Rhythm 0x04, Beat 0x06, Spray 0x07, Bounce 0x08, Separation 0x32, Skittles 0x4D, Candy Crush 0x4E, Fusion 0x4F, Torch 0x50, Shiny 0x51 | Own codebook derived from the schema enum, so shared H617A codes are not reused |
| Legacy parameters | Capture and app legacy music selector builder: a fixed-colour flag then RGB; Rhythm has a leading Dynamic byte where one is Dynamic | Style and fixed colour in the selector |
| Companion bodies | Capture (Torch, Separation) and app music companion serialiser: A3 command `0x41`, mode, seven default colours, and for Separation the tail `02 00 61` | `h6076_music_body.ksy`; Torch and Separation captured, the other four follow the app producer only.  Other effects carry no tail in the app's default bodies |
| Separation tail | App Separation parameter builder: point, fade flag and a speed byte of 94 or 97 below 30 ICs and 98 or 99 from 30, for fade on or off; the captured `0x61` is `97` | Captured default only; the lamp's IC count is unknown, so no authored parameters |
| Order and acknowledgement | The app uploads the A3 music companion before sending the selector; the capture shows an `a3 41 <mode> 00` reply per body | Upload before selector; `h6076_music_ack.ksy` models the reply and an acknowledgement counts only when it repeats the uploaded mode, which the app itself does not check |
| Independent replay | The reporter's LAN integration builds the same selector and companion bytes for all twelve effects at full sensitivity (checked byte for byte against this implementation) and reports that every effect and the sensitivity react on an H6076 | Corroborates the logical frames, including the four bodies that were not captured in full.  It is plaintext over the LAN API, so it says nothing about Bluetooth, V1 or the gate |
| Software gate | App floor-lamp capability gate: pact 1/1 or 2/1 with software 1.02.00 or newer uses these effects; older software uses a legacy screen | Identity-qualified profile; everything else keeps the basic controls |
| Music screen | App music UI configuration picks the richer music screen over the default effect list for hardware 3.01.01 with software above 1.03.06 or hardware 3.05.00 with software 1.04.01 or newer; both screens send the same frames | Not a gate: it selects a screen, not a wire dialect.  Owners report whether the lamp reacts to sound |

## Candidate support scope

Qualified lamps expose twelve effects as light effects and in Effect Studio native music, sensitivity 0 to 99, a fixed colour for the six legacy effects, Dynamic or Calm for Rhythm, and the app's default companion for the six companion-backed effects.

Phone microphone streaming is a repository non-goal.  Authored palettes and parameters for companion effects, music readback, and software older than 1.02.00 remain unavailable until captures exist.  The lamp does not answer the colour-mode query, so music state is the last command, not an observation.

## Model-specific changes and owner checks

| Obligation | Owner | Runnable evidence |
| --- | --- | --- |
| Pact and software gate | `const.device_profile`, `coordinator._resolve_device_profile` | `tests/test_const.py`, `tests/test_coordinator.py` |
| Selector, companion and reply layouts | `h6076_music_write.ksy`, `h6076_music_body.ksy`, `h6076_music_ack.ksy`, `generated_protocol_adapter` | `tests/test_kaitai_protocol.py`, `tests/test_music_commands.py`, `tests/test_upload_ack.py` |
| Codebook, style and companion modes | `music_protocol`, `music_semantics` | `tests/test_model_music_protocol.py` |
| Identity and music over V1 | `govee_encryption`, coordinator | `tests/test_govee_encryption.py` |
| Light and Effect Studio exposure | `effect_catalogue`, `effect_contracts` | `tests/test_light.py`, `tests/test_effect_catalogue.py` |

The owner installs the prerelease through HACS and restarts Home Assistant.  They then use the lamp the way they normally would and report what looks wrong.

- **Everyday controls still work.**  Power, brightness, colour and colour temperature, including after a Home Assistant restart.
- **The music effects appear and respond.**  Play some music near the lamp and try the twelve effects.  Note any that do nothing or look different from the Govee app.
- **Style and colour make a difference.**  Set Rhythm to Calm, give a few effects a fixed colour, and move the sensitivity between low and high in the Effect Studio music profile.
- **It behaves over time.**  Leave it idle and come back, switch between the Govee app and Home Assistant, and restart Home Assistant while an effect is playing.

If anything fails, the owner exports diagnostics straight afterwards.  The diagnostics show the pact, software and hardware versions, the transport, and the lamp's replies, which is enough to tell a gate problem from a wire problem.

The fixed colour, Calm and the four effects not captured over Bluetooth (Skittles, Candy Crush, Fusion and Shiny) are the least certain parts, so reports on those matter most.  If an effect keeps timing out, the `a3` reply lines in the diagnostics packet log show whether the lamp repeats the mode, because a reply that does not is ignored.  Reports that the basics work and that effects react are the bar for physically qualifying the music addition.  Until then, the existing Partial model label and speculative evidence remain unchanged.  A second owner on hardware 3.01.01 with plaintext, as in [#247](https://github.com/teh-hippo/ha-govee-led-ble/issues/247), would show whether the mode reply holds there too.

Tests establish software boundaries, not hardware compatibility.
