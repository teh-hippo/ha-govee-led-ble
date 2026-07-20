# Govee H6199 DreamView T1 BLE protocol reference

This document records the H6199 protocol observed by passively sniffing Govee Home while it drove
the captured DreamView T1. The scope is hardware `3.02.01`, firmware `1.10.04`, using the V2
command family. The H6199 is never direct-driven by development Bluetooth tooling.

## Transport and command families

Frames are 20 bytes. `byte[19]` is the XOR of bytes 0 through 18, and unused payload bytes are
zero-padded.

| Header or selector | Meaning |
| --- | --- |
| `0x33` | Command from the app to the device. |
| `0xAA` | Query or device status. |
| `0xA3` | Multi-frame body upload. |
| `33 05 00` | DreamView video mode. |
| `33 05 04` | Scene activation. |
| `33 05 0A` | DIY activation. |
| `33 05 13` | V2 music mode. |
| `33 05 15` | V2 colour family. |
| `33 A9` | DreamView advanced controls. |

Older H6199 firmware may use `0x0C` and `0x0B` for music and colour. Those generations are outside
the captured and supported scope.

## Command reference

| Feature | Frame | Semantics and evidence |
| --- | --- | --- |
| Power | `33 01 <on>` | `00` off, `01` on. |
| Brightness | `33 04 <pct>` | Whole-device brightness, 0 to 100. It is not part of the video frame. |
| RGB colour | `33 05 15 01 <R G B> 00 00 00 00 00 FF 7F` | V2 whole-device colour. |
| Colour temperature | `33 05 15 01 00 00 00 <Khi Klo> <wR wG wB> FF 7F` | Confirmed live: the command and big-endian kelvin word (`[7:9]`) are byte-identical to the shared builder (captured `0x0E10` = 3600 K). The white-preview RGB uses a slightly different kelvin-to-RGB curve than `build_color_temp`, which is cosmetic because the device selects white from the kelvin word. |
| Video mode | `33 05 00 <region> <mode> <sat> <sound> <softness>` | Full payload is always sent. `region`: all `01`, part `00`; `mode`: movie `00`, game `01`; saturation 0 to 100; sound `00` or `01`; softness 1 to 100. |
| Music mode | `33 05 13 <mode> <sensitivity> ...` | Confirmed modes: Rhythm `03`, Spectrum `04`, Energetic `05`, Rolling `06`. Style, count, and RGB fields are not confirmed for this model. |
| Simple scene | `33 05 04 <code_LE> 01` | Type `01` activation without an A3 body. |
| A3 scene | `A3 ...`, then `33 05 04 <code_LE> 02` | Type `02` activation after a type-`02` scene body. |
| Flat DIY sample | `A3` type `04`, then `33 05 0A 61` | Fade1 proves that H6199 exposes DIY and uses a model-specific activation slot. Wider authoring remains gated. |
| White balance | `33 A9 00 03 01 <red> <blue>` | Two independent raw axes. There is no proven one-dimensional conversion. |
| Blank Screen | `33 A9 0A 06 <enabled> 02 0A 00 78 00` | Enable is attributable and the observed duration is two minutes. Other fields are not decoded. |
| Hardware query | `AA 07 03` | Reply selector `03`, then ASCII hardware version `3.02.01`. |

The app retained the softness byte while sound was off, including the observed minimum `0x01`.
Do not omit the sound and softness fields when reproducing the current app frame.

The broader `0xA9` family also carries controls for sensitivity, HDR, automatic white balance, AI
filtering, and black-screen or border handling. Their layouts are not yet attributable.

## Video status

No attributable `AA 05` video-mode reply has been captured. The shared parser can decode a
candidate payload as:

```text
00 <region> <mode> <saturation> <sound> <softness>
```

This remains a hypothesis until a marked app-sniff captures the device reply. Command validation
does not prove read-back layout.

## Implementation status

The H6199 model profile currently exposes:

- power, brightness, RGB, and colour temperature;
- movie and game video modes, region, saturation, sound, and softness;
- the four confirmed music modes;
- whole-strip white brightness through the H617A-derived segment-brightness command.

The following implementation details require care:

- `build_h6199_scene` reproduces the captured simple and A3 activation forms, but the H6199 scene
  catalogue is not exposed by the light entity.
- `build_video_white_balance` emits the confirmed raw two-axis frame, but no Home Assistant entity
  exposes it because the app control mapping is not known.
- `build_video_mode` always emits the full frame `33 05 00 <region> <mode> <sat> <sound> <softness>`,
  matching the app. Softness persists when sound is off and is floored at `0x01`.
- `build_color_temp` is confirmed live on H6199: the command and big-endian kelvin word match the
  shared builder byte-for-byte. Only the embedded white-preview RGB differs, because the app's
  kelvin-to-RGB curve is not identical to `kelvin_to_rgb`; the device selects white from the kelvin
  word, so the preview delta is cosmetic.
- Whole-strip white brightness uses `33 05 15 02` with mask `0x7FFF`, inherited from H617A. No
  H6199 write in this command family is attributable, so this exposed surface is not yet
  H6199-validated.
- H6199 reports 15 segments, but no attributable segment write has been captured. Segment services
  and static segment effects remain disabled.
- DIY, timers, and power-off memory remain disabled for this model.

## Verification backlog

1. Capture a marked `AA 05` reply while video mode is active.
2. Map the white-balance UI to both independent raw bytes.
3. Attribute `33 05 15 02` before treating whole-strip white brightness as validated.
4. Attribute representative H6199 scenes and expose the model-specific catalogue only after
   parity checks.
5. Capture DIY speed and a second family before implementing H6199 authoring.
6. Attribute a segment write before enabling any segment surface.
7. Confirm whether music style or colour fields exist on H6199.
8. Decode Blank Screen, per-side brightness, and the remaining `0xA9` controls.
