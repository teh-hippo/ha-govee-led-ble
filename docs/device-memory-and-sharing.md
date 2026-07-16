# Govee device memory model and portable effect sharing

What the physical device actually stores and understands, versus what lives in the app/cloud, and
how a custom effect can be shared as a **self-contained, cloud-free blob**. Determined by live BLE
capture against the device and analysis of the app's on-wire behaviour. Applies to the RGBIC family
(H617A and siblings); the TV family (H6199) is similar for scenes/DIY.

## 1. Device vs app/cloud responsibility

**The device stores only:**

- **A small fixed set of built-in, firmware-resident scenes**, addressed by numeric code and
  applied **activation-only, with no upload**: 12 codes `{0,1,4,5,7,8,9,10,15,16,21,22}` are
  activated with `33 05 04 <code>`. Code-only apply is the proof the firmware holds these itself.
- **The current "what am I showing" pointer.** On reconnect the device answers `AA 05` with its
  live selection: current scene code, DIY code or colour. The app **reads** state, it does not
  assume it.
- **A power-off-memory setting**: command `0x41`, query `AA 41`:
  restore-last-state on/off, or restore a fixed configured mode. Model/version gated.
- **Raw numeric records only**: colour `33 05 15 01`, per-segment, brightness, and effect record
  containers. The app serialises everything to bytes before sending; the device stores no names or
  structured objects.

**The app/cloud stores everything else:**

- The user's **whole DIY library is cloud-side** (list/detail/effect strings are fetched by id).
  Save/create posts the full record (name, effect string and effect codes).
- **Custom DIY is re-uploaded to the device on every apply, then activated by code**: the app
  never trusts the device to have kept it (transport `0xA1` cmd `0x02`, then `33 05 0A <code>`).
  The asymmetry (built-in scenes = code-only; custom DIY = upload-then-activate) is the core
  evidence that **custom effects are not device-persisted**.
- **Snapshots are an app/cloud store, not a device feature** (the app uploads snapshot blobs to the
  server). No device-side snapshot command exists.

## 2. Naming and slots

- **Names are never sent to the device.** They exist only in the app's packaged scene catalogue
  and cloud metadata. Every wire write carries codes/bytes only. Any "name" in our integration is
  our own concept.
- **There are no device-side addressable slots.** Nothing in the app's traffic references a slot,
  preset or memory-slot index. The byte after `33 05 04` / `33 05 0A` is a 2-byte **effect code**
  (a content handle re-uploaded each apply), not a firmware slot index.

## 3. Persistence across power cycles

- **Firmware retains:** the built-in scenes (code replay), the active-mode pointer (via `AA 05`),
  and the power-off-memory behaviour (`AA 41`).
- **App re-pushes on apply (never trusts to survive):** custom DIY bodies (`0xA1`) and rich/cloud
  scene bodies (`0xA3`), each followed by a code activation. On connect the app **reads** state
  and does not re-upload effect bodies.
- **Unprovable from the app:** whether firmware keeps a *full custom-effect body* across a hard
  power-cycle; the app always re-uploads a custom DIY before activating it.

## 4. Portable custom-effect sharing (cloud-free)

Govee has two "share" systems. Its social share hands over a **cloud web link** referencing a
server `videoId`, not useful to us. But the effect payload itself is a **self-contained base64
blob**, which is the model we want.

**Minimal fields to reconstruct and apply with no cloud:** `sku` + `sceneType` +
`effectStr` (base64 record bytes) + activation `code`. Everything else (author, cover, `videoId`,
`effectId`) is metadata. The recipient path is cloud-free:
`base64 decode → parse leading discriminator byte → build 01 <lineCount> <sceneType> + records →
fragment into 0xA3 frames → activate 33 05 04 <code> (scene/rgbicv2) or 33 05 0A <code> (flat DIY)`.
Our `build_scene_multi` already replays this byte-for-byte.

**Proposed export format** (`docs`-owned, for our own import/export, not Govee's):

```json
{
  "fmt": "ha-govee-effect", "v": 1,
  "model": "H617A",                        // selects parser + activation opcode; MANDATORY
  "sceneType": 2,                           // transport TYPE byte (0x01 or 0x02)
  "activation": { "op": "0504", "code": 506 },  // 33 05 04 <code>, or op "050a" for flat DIY
  "effect_b64": "AyYAAQAK…",                // == Govee effectStr: raw record-container bytes
  "name": "My Bloom"                        // optional, app-side only
}
```

Guardrails: `model` is mandatory (the same `effect_b64` parses differently per SKU); no `videoId`/
`effectId`/author/icon is needed to drive the device; names are display-only. For a per-segment
"paint", the app's per-segment share blob is already a complete, versioned, cloud-free format
(version byte + background RGB + `colour → [segment index…]` map) worth copying verbatim.

Provenance: confirmed by live BLE capture against the device and analysis of the app's on-wire
behaviour.
