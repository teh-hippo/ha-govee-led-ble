# Govee effect catalogue (scenes + DIY) and test plan

Companion to [`ble-protocol-h617a.md`](ble-protocol-h617a.md). That document covers the
transport, command set and multi-frame packet framing; this one is about the **content**: the
full list of effects the device can play, where the list comes from, and how to test them
without capturing each one by hand.

There are three kinds of effect, from different sources:

1. **Scenes** (named presets like "Aurora", "Halloween", "Bloom"). The complete list per
   model is served by a public Govee endpoint, and each scene carries the exact BLE payload.
   This means we can enumerate and test **every** scene today, no capture required.
2. **DIY custom effects** (33 user-authored effects built in the app's DIY editor: animation
   families such as Fade, Jumping, Marquee and Rainbow, richer templates such as Bloom and
   Sparkle, the freeform "Finger Sketch", and chained "Combo" effects), applied to colour
   palettes the user picks. These are built client-side and are **not** in any public list; they
   are encoded directly in the BLE body. This session decoded and **confirmed on-wire** the
   **four** distinct DIY body encodings and the complete 33-effect catalogue. See section 2.
3. **Vibrant** (a multi-colour gradient), not yet implemented: the user picks 2 to 5 colours and
   the app interpolates them across the strip's 15 segments, then uploads the resolved
   per-segment colours. Unlike scenes and animated DIY it plays no animation. Vibrant reuses the
   Finger Sketch `TYPE 0x03` encoding (section 2.4). See section 3 and
   [`ble-protocol-h617a.md`](ble-protocol-h617a.md).

## Model identification

The captured device is an **H617A** (originally assumed to be an H619A). Several independent
signals confirm the model:

- The captured "Halloween" scene used code **1173**. That is H617A's code for Halloween; on
  H619A/H6199 the same scene is code **2497**. (Fetched live from the Govee library API below.)
- Home Assistant's Bluetooth scan advertises this strip as `Govee_H617A_*` (never `H619A`).
- The generated `scenes.py` catalogue is mechanically checked against the frozen H617A snapshot.

Practical upshot: the scene work is essentially done (H617A is already supported), and the new
capabilities to add are **per-segment control**, **DIY custom effects** and the **Vibrant
gradient**. The H619A/H6199
data is retained here too, since H619A and H6199 share one catalogue (verified byte-identical)
and H6199 is already a supported model.

## Source: the Govee light-effect library API (no account needed)

The Govee app fetches its scene catalogue from an undocumented but key-less endpoint:

```
GET https://app2.govee.com/appsku/v1/light-effect-libraries?sku=<SKU>
Header: AppVersion: 9999999
```

No token or login is required (only the `AppVersion` header). The response groups scenes by
category, and each scene's `lightEffects[].scenceParam` is a base64 blob that **is** the BLE
payload: decode it, chunk it into `0xA3` multi-frames, and finish with `33 05 04 <code>`. That
is exactly what `build_scene_multi()` already does, and it matches the reference
implementations in `wez/govee2mqtt` (`src/ble.rs`) and `AlgoClaw/Govee`
(`decoded/v1.2/explanation_v1.2.md`).

Fetch and distil the catalogue for any model with the helper tool:

```bash
uv run python tools/ble/fetch_effect_library.py H617A H6199
uv run python tools/ble/fetch_effect_library.py H617A H6199 --check
uv run python tools/ble/generate_scenes.py --check
```

Each distilled entry is `{category, name, code, param, variant?, adjustable?, config?}`, which
is enough to send the scene (`build_scene(code)` for simple scenes, or
`build_scene_multi(param, code)` when `param` is present) and to know which parameters it
exposes (`config`). Frozen snapshots live under `tools/ble/catalogues`; `--check` reports added,
removed and changed entries without overwriting them. `generate_scenes.py` keeps the compressed
H617A runtime catalogue in `scenes.py` mechanically aligned with its frozen snapshot.

## 1. Scenes (H617A, complete)

80 scenes across 5 categories. Codes are the `sceneCode` used in `33 05 04 <code_LE>`. A `~`
marks scenes that expose adjustable parameters (speed/brightness, see section 4); scenes
without a `param` (e.g. Sunrise/Sunset) are activated by the code alone.

### Natural (32)
Sunrise(0), Sunset(1), Forest(2163)~, Aurora(2164)~, Lightning A(2165)~, Lightning B(2278)~,
Starry Sky(2166)~, Spring(2167)~, Summer(2168), Fall(2169), Winter(2170)~, Rainbow(22),
Fire(2171)~, Wave(2172)~, Deep sea(2173)~, Karst Cave(2174)~, Glacier(2175)~, Gobi
Desert(2176)~, Moonlight(2177)~, Flower Field(2178)~, Downpour(2179)~, Sunny(2180)~, Volcano
A(2181)~, Volcano B(2277)~, Cornfield(2182)~, Meteor shower(2183)~, Flying(2184), Tree
shadow(2185), Cherry blossoms(2186)~, Stream(2187)~, Ripple(2188)~, Desert B(10005), Sand
Grains(10006), Aurora B(16160).

### Festival (9)
Christmas(2189)~, Halloween(1173), Candlelight(9), Birthday(2190), Fireworks(2191)~,
Party(2192)~, Dance Party(2193)~, Mother's Day(2194)~, Father's Day(2195)~.

### Life (15)
White Light(10565), Sweet(1170), Romantic(7), Movie(4), Siren(2196)~, Night(2197),
Sleep(2198), Morning(2199), Afternoon(2200), Work(2201), Leisure(2202)~, Meditation(2203),
Colorful(2204)~, Candy(2205), Dreamlike(2206)~.

### Emotion (15)
Dreamland A(2207)~, Dreamland B(2279)~, Energetic(16), Profound(2208)~, Quiet(2209),
Warm(2210)~, Flow(2211)~, Longing(2212), Happy(2213)~, Mysterious(2214)~, Release(2215)~,
Game(2216)~, Disco(2217)~, Optimistic(2218), Heartbeat(2219)~, Cheerful(2220)~.

### Funny (9)
Swing(2222)~, Flash(2223)~, Fight(2224)~, Stacking(2225)~, Twinkle(8), Breathe(10),
Spin(2226)~, Rhythm(2227), Bloom(2228)~.

> Note: "Bloom" and "Rainbow" here are **scenes**, distinct from the DIY families of the same
> name in section 2. The scene versions play a fixed Govee-authored animation; the DIY
> versions apply the chosen animation to a user palette.

The generated H617A runtime catalogue now carries all 83 effect variants across the 80 scene
tiles, including **Aurora B** (16160), and is checked against the frozen API snapshot.

`SceneEntry` carries the API `sceneType`, and `build_scene_multi()` passes it to the A3 fragmenter.
This preserves the `0x01` prefix required by **Halloween** and **Sweet** instead of assuming the
common `0x02` type.

### H619A / H6199 scenes
149 scenes across 12 categories (including licensed packs: "House of the Dragon", "Zootopia
2", "Miami Dolphins"), plus Music/Games/Movie categories absent from H617A. The codes differ
from H617A (e.g. Halloween 2497 vs 1173, Forest 212 vs 2163), so H619A/H6199 need their own
catalogue. Regenerate with `fetch_effect_library.py H6199`.
The captured simple and type-`0x02` branches are byte-pinned in `build_h6199_scene`; the H6199
catalogue is not yet surfaced by the light entity.

## 2. DIY custom effects

A DIY effect is a user-authored effect built in the app's DIY editor: an animation family (or a
richer template), a variant, a speed, and one or more colour groups. The integration does
**not** implement DIY yet (it encodes scene mode `0x04` only). Every value below was **confirmed
on-wire this session** on the H617A unless explicitly marked inferred.

### 2.1 Four body encodings

Every DIY effect uploads its definition as `0xA3` multi-frames whose reassembled body begins
`01 <linecount> <TYPE> ...`, the same framing as scenes and Vibrant (byte-level detail in
[`ble-protocol-h617a.md`](ble-protocol-h617a.md), section 6). The `TYPE` byte selects one of
four encodings, and the encoding also fixes how the effect is activated:

| Encoding | `TYPE` | Body after `01 <linecount> <TYPE>` | Activation | Effects |
|---|---|---|---|---|
| Flat | `0x04` | `FAMILY VARIANT SPEED PLEN <palette>` | `33 05 0a <slot>` | Fade, Jumping, Twinkle, Marquee, Chasing, Rainbow, Crossing, Music |
| rgbicv2 | `0x02` | record container (scene-style) | `33 05 04 <code_LE>` | Brilliant, Colorful starry sky, Colorful meteor, Colorful meteor shower, Sparkle, Bloom, Stack |
| Finger Sketch | `0x03` | `EFFECT SPEED BRIGHT <bg RGB> <paint groups>` | `33 05 0a <slot>` | Finger Sketch (freeform paint) |
| Combo | `0x04`, `FAMILY = 0xFF` | flat body + trailing `(family, variant)` pairs | `33 05 0a <slot>` | up to 4 chained flat effects |

Two activation paths:

- **Flat, Finger Sketch and Combo** activate with mode `0x0a` and a per-DIY **slot** id, an
  app-assigned handle (observed `0xF0`; an earlier Fade capture used `0xBE`). The slot is not a
  catalogue code and carries no colour information.
- **rgbicv2** activates with the **scene** command `33 05 04 <code_LE>`, each effect owning its
  own code (2.3). Because the transport is byte-for-byte the scene path, feeding a captured
  rgbicv2 body to the existing `build_scene_multi(base64(body[3:]), code)` reproduces its frames
  and activation exactly (confirmed).

`TYPE` alone is not unique: rgbicv2 DIY shares `0x02` with scenes, and Vibrant shares `0x03` with
Finger Sketch, so the encoding is identified by `TYPE` **and** activation command together.

### 2.2 Flat encoding (`TYPE 0x04`)

The reassembled body (offsets counted from the leading `01`):

```
offset:  0   1            2    3        4         5       6      7 ..
byte:    01  <linecount>  04   FAMILY   VARIANT   SPEED   PLEN   <palette RGB...>
                          |    |        |         |       |      |
                          |    |        |         |       |      PLEN bytes = colours x 3
                          |    |        |         |       palette length in bytes
                          |    |        |         SPEED 1..100, default 0x32 = 50 (UI floor 1)
                          |    |        family-specific variant selector (no global formula)
                          |    animation family (equals the app's internal effect-family code)
                          flat DIY protocol code (fixed marker)
```

- `FAMILY` equals the app's internal effect-family code, a useful cross-check: Fade 0, Jumping 1,
  Twinkle 2, Marquee 3, Music 4, Chasing 8, Rainbow 9, Crossing 10 (`0x0a`). (Confirmed.)
- `VARIANT` is **family-specific with gaps**, not a clean 0-based index. The confirmed pairs are
  tabulated in 2.6; there is no formula, so each `(family, variant)` must be recorded
  empirically.
- `SPEED` sits at offset 5. For the **Music** family this slot instead carries a **Sensitivity**
  value (observed `0x64` = 100), not speed.
- `palette` is ordered RGB triplets. The editor's default palette is the seven colours
  `FF0000 FF7D00 FFFF00 00FF00 0000FF 00FFFF 8B00FF`.

Worked example (Jumping1, seven colours, default speed), activation `33 05 0a f0`:

```
01 02 04 01 00 32 15  FF0000 FF7D00 FFFF00 00FF00 0000FF 00FFFF 8B00FF
      |  |  |  |  |    \_________________ 21 palette bytes _________________/
      |  |  |  |  PLEN = 0x15 = 7 x 3
      |  |  |  SPEED = 0x32 = 50
      |  |  VARIANT = 0x00 (Jumping1)
      |  FAMILY = 0x01 (Jumping)
      protocol code 0x04 (flat)
```

Confirmed on-wire: Fade1 -> Fade2 changed only `VARIANT`; Marquee1 (`0x03`) -> Marquee2 (`0x04`)
incremented `VARIANT` by one; sweeping the colour count 6 -> 3 tracked `PLEN` through
`0x12, 0x0f, 0x0c, 0x09`; the speed slider moved only offset 5 between `0x01` and `0x64`.

### 2.3 rgbicv2 encoding (`TYPE 0x02`)

The "rich" DIY effects (two colour groups, relative-brightness ranges, star sizes, directions)
use a **record container** body transported and activated exactly like a Govee scene. The
reassembled body is `01 <linecount> 02 <record container>`, and each effect is activated with
`33 05 04 <code_LE>` using its own code:

| Effect | Code | LE activation | Colour groups | Variant / parameters |
|---|---|---|---|---|
| Brilliant | 501 | `33 05 04 f5 01` | single 1..8 | speed 76..255, default 250; no direction; no user brightness; variant = `param2` (`0x32`/`0x14`) |
| Colorful starry sky | 502 | `33 05 04 f6 01` | single 1..8 | star-size range (observed ~1..12) + relative brightness + speed |
| Colorful meteor shower | 503 | `33 05 04 f7 01` | single 3..8 | body ~102 bytes; direction; variant body byte |
| Colorful meteor | 504 | `33 05 04 f8 01` | single 1..8 | body ~51 bytes; direction; variant body byte |
| Sparkle | 505 | `33 05 04 f9 01` | embellishment 1..8 + fixed 1 background | relative-brightness interval + speed |
| Bloom | 506 | `33 05 04 fa 01` | bloom 1..8 + moving 1..8 | no speed slider; relative brightness; variant = body offset 99 (`0x14`/`0x16`) |
| Stack | 507 | `33 05 04 fb 01` | stack 1..8 + moving 1..8 | relative brightness 1..100; direction |

Key facts (confirmed):

- Codes are **per-effect and externally assigned**, all in a ~500 band that contains no catalogue
  scenes. They are not derived from the body and not the app template id (for example Bloom's
  template id is 113, but its activation code is 506).
- The **variant** (Bloom1 vs Bloom2, Brilliant1 vs Brilliant2) is a **body byte**, not a code
  change: both variants of an effect share one code.
- Because the transport is the scene path, the integration can **replay** any captured rgbicv2
  DIY today via `build_scene_multi`; only the `(body, code)` pair needs storing. The record
  grammar is now fully decoded ([`ble-protocol-h617a.md`](ble-protocol-h617a.md) section 6), so
  synthesising a body from scratch is feasible; the remaining unknowns are the concrete per-effect
  speed-lookup values and the exact pixel-level delta between numbered sub-styles (inferred).

**Direction vocabulary (confirmed).** The rgbicv2 movement engine exposes four directions:
Forward, Backward, Forward and Backward, and Backward and Forward. An effect that offers a
direction control presents a subset through a per-effect picker (Colorful meteor, Colorful meteor
shower and Stack show Clockwise / Counterclockwise), which a linear strip renders as forward or
backward. Flat effects (2.2) expose only Clockwise / Counterclockwise (Chasing, Rainbow) or none.

Per-effect colour-group ranges, speed domains and directions are in 2.7.

### 2.4 Finger Sketch encoding (`TYPE 0x03`)

Finger Sketch is a freeform paint tool, not a family+variant primitive: the
user paints segments and the app uploads the painted layout. Body:

```
offset:  0   1            2    3        4       5        6 7 8      9             10 ..
byte:    01  <linecount>  03   EFFECT   SPEED   BRIGHT   <bg RGB>   <groupcount>  [<segcount> <fill RGB> <segment index...>] ...
                          |    |        |       |        |          |
                          |    |        |       |        |          one or more paint groups follow
                          |    |        |       |        background colour (RGB)
                          |    |        |       brightness (observed 0x64 = 100)
                          |    |        SPEED (50% -> 0x33, max -> 0x64)
                          |    EFFECT motion code (table below)
                          Finger Sketch type byte
```

Each paint group is `<segment count> <fill RGB> <segment index...>`, so a group paints a set of
segments one colour; multiple groups give multiple fill colours. **Segment indices are 0-based**
and match the colour-mask bit numbering (segment 0 is the first segment).

Motion codes (`EFFECT`, offset 3), all confirmed by cycling the dropdown:

| Motion | `EFFECT` |
|---|---|
| Cycle | `0x02` |
| Clockwise | `0x09` |
| Counter-clockwise | `0x0A` |
| Twinkle | `0x0F` |
| Gradient | `0x13` |
| Breathe | `0x14` |

Worked example (Clockwise, background blue, one group of four green segments), activation
`33 05 0a f0`:

```
01 <lc> 03 09 33 64  00 00 FF  01  04  00 FF 00  00 01 02 04
        |  |  |  |    \bg blue/ |   |   \fill  /  \_ segs 0,1,2,4 _/
        |  |  |  BRIGHT 0x64    |   segment count = 4
        |  |  SPEED 0x33 (50%)  paint group count = 1
        |  EFFECT 0x09 (Clockwise)
        TYPE 0x03
```

Finger Sketch has **no colour-group min/max**; it is freeform per-segment paint. Vibrant
(section 3) is the same `TYPE 0x03` family: it uses `EFFECT = 0x09` with the speed byte `0x00`
and a static 15-segment gradient rather than paint groups.

### 2.5 Combo encoding (`TYPE 0x04`, `FAMILY 0xFF`)

Combo chains up to four flat effects behind one shared palette and speed. It reuses the flat
encoding with the reserved family `0xFF`:

```
01 <linecount> 04 FF <var> <speed> <plen> <palette...> <seqlen> <(FAMILY, VARIANT) pairs>
```

- `seqlen` = `2 x number_of_effects` (two bytes per chained effect).
- Each pair is a `(FAMILY, VARIANT)` from the flat table (2.2).
- There is one shared colour list and one speed; there are no per-effect parameters.

Confirmed example, Fade1 + Marquee1 (seven-colour palette), activation `33 05 0a f0`:

```
... 15 <7 colours> 04 00 00 03 03 00
    |              |  \___/ \___/ |
    |              |  Fade1 Marq1 trailing pad
    |              seqlen = 0x04 (2 effects)
    PLEN = 0x15
```

Pair `(00, 00)` is Fade1 and `(03, 03)` is Marquee1, matching the flat `(FAMILY, VARIANT)`
values. The app caps a Combo at four effects. The `seqlen` scaling is **confirmed**: building
Fade1, Jumping1, Marquee1 then Chasing1 stepped `seqlen` through `0x02, 0x04, 0x06, 0x08`
(`2 x effect_count`), with pairs `(00,00)(01,00)(03,03)(08,09)` accumulated in order.

### 2.6 Complete DIY effect catalogue (33 effects)

Every DIY effect captured this session, grouped by encoding. "Colours" is the editor's practical
colour-group range (the app config minimum is 0 for flat effects; see 2.7 for the authoritative
per-effect limits, the rgbicv2 speed domain and directions).

**Flat (`TYPE 0x04`, activation `33 05 0a <slot>`)**

| Effect | `FAMILY` | `VARIANT` | Colours | Notes |
|---|---|---|---|---|
| Fade1 | `0x00` | `0x00` | 1..8 | |
| Fade2 | `0x00` | `0x01` | 1..8 | |
| Fade3 | `0x00` | `0x02` | 1..8 | |
| Jumping1 | `0x01` | `0x00` | 1..8 | |
| Jumping2 | `0x01` | `0x02` | 1..8 | variant skips `0x01` |
| Twinkle1 | `0x02` | `0x00` | 1..8 | |
| Twinkle2 | `0x02` | `0x01` | 1..8 | |
| Twinkle3 | `0x02` | `0x02` | 1..8 | |
| Marquee1 | `0x03` | `0x03` | 1..8 | |
| Marquee2 | `0x03` | `0x04` | 1..8 | |
| Marquee3 | `0x03` | `0x05` | 1..8 | |
| Chasing1 | `0x08` | `0x09` | 1..8 | |
| Chasing2 | `0x08` | `0x0a` | 1..8 | |
| Rainbow1 | `0x09` | `0x09` | 1..8 | |
| Rainbow2 | `0x09` | `0x0a` | 1..8 | |
| Crossing | `0x0a` | `0x00` | 1..**3** | displays as "Crossing"; bidirectional crossing of up to 3 bands (fallback: one-way 3-colour chase); only flat effect capped below 8 |
| Music1 | `0x04` | `0x08` | 1..8 | Sensitivity in the SPEED slot; DIY Music, not the app Music mode |
| Music2 | `0x04` | `0x06` | 1..8 | |
| Music3 | `0x04` | `0x07` | 1..8 | |

**rgbicv2 (`TYPE 0x02`, activation `33 05 04 <code_LE>`)**

| Effect | Code | Colour groups | Variant selector | Notes |
|---|---|---|---|---|
| Brilliant1 | 501 | 1 background + 4..8 embellishment | body shape | Speed + relative-brightness interval 10..100%; current iOS body has 7 A3 parts |
| Brilliant2 | 501 | 1 background + 4..8 embellishment | body shape | Same controls; current iOS body has 6 A3 parts |
| Colorful starry sky | 502 | single 1..8 | body byte | star-size range ~1..12 + relative brightness + speed |
| Colorful meteor1 | 504 | single 1..8 | ~`0x20`/`0x29` | body ~51 bytes; direction |
| Colorful meteor2 | 504 | single 1..8 | body byte | |
| Colorful meteor shower1 | 503 | single 3..8 | ~`0x20`/`0x29` | body ~102 bytes; direction |
| Colorful meteor shower2 | 503 | single 3..8 | body byte | |
| Sparkle | 505 | embellishment 1..8 + fixed 1 background | body byte | relative-brightness interval |
| Bloom1 | 506 | bloom 2..8 + moving 2..8 | body shape | 7-part current iOS body; relative brightness 1..100% |
| Bloom2 | 506 | bloom 2..8 + moving 2..8 | body shape | deterministic 9-part body |
| Bloom3 | 506 | bloom 2..8 + moving 2..8 | body shape | deterministic 9-part body |
| Stack1 | 507 | stack 1..8 + moving 1..8 | body byte | relative brightness 1..100 |
| Stack2 | 507 | stack 1..8 + moving 1..8 | body byte | |

**Finger Sketch (`TYPE 0x03`, activation `33 05 0a <slot>`)**

| Effect | Motion codes | Colours | Notes |
|---|---|---|---|
| Finger Sketch | 6 (see 2.4) | freeform | per-segment paint, no colour-group limit |

That is 19 flat + 13 rgbicv2 + 1 Finger Sketch = **33 distinct DIY effects** (all "Single" mode).
**Combo** (2.5) is a separate DIY mode that chains flat effects; it is not counted among the 33.

The H617A serves exactly these 33. The Govee app carries further templates (Progress /
Ladder, Battle / Duikang, Sway / Swing, Spin / Revolve, Vibrate / Penshe, Stacking / PileUp,
Colorful, Chase), but those belong to other RGBIC SKUs (H604A/B, H605B, H6608, H66013), not the
H617A, so this catalogue is complete for the H617A.

Current iOS 7.5.21 editors apply selections and parameter changes immediately; the visible Apply
button is not the BLE write boundary. Bloom2 relative brightness 10/30/10% produced repeatable
wire values `0x45/0x6f/0x45`. Share Space replays a downloaded four-part A3 body through DIY
activation `0xfe`. Workshop and AI/image effects remain separate authoring/import mechanisms.

The H6199 also exposes DIY, but its captured Fade1 uses activation `0x61`. H617A animated DIY
builders must not be reused for H6199 until that model's body grammar is mapped.

Effect appearance (motion) is confirmed only for Brilliant (a brisk flow of the chosen colours, no
direction) and Crossing (a bidirectional crossing of up to three bands); the per-variant spatial
behaviour of the other families is still inferred. Full motion descriptors are kept in internal
analysis notes.

### 2.7 Colour and parameter limits

Authoritative per-effect limits observed from the app. These are the app-enforced
bounds; the captures this session all sit inside them.

**Flat effects** (colour config minimum is 0, but the editor requires at least 1 in practice):

| Effect | `FAMILY` (family code) | Colours | Speed (min/max/def) | Sub-effects (style / direction) |
|---|---|---|---|---|
| Fade | `0x00` (0) | 0..8 | 0 / 100 / 50 | Whole, Subsection, Circulation |
| Jumping | `0x01` (1) | 0..8 | 0 / 100 / 50 | Whole, Circulation |
| Twinkle | `0x02` (2) | 0..8 | 0 / 100 / 50 | Whole, Subsection, Circulation |
| Marquee | `0x03` (3) | 0..8 | 0 / 100 / 50 | All, Gathered, Dispersive |
| Chasing | `0x08` (8) | 0..8 | 0 / 100 / 50 | Clockwise, Counterclockwise |
| Rainbow | `0x09` (9) | 0..8 | 0 / 100 / 50 | Clockwise, Counterclockwise |
| Crossing | `0x0a` (10) | 0..**3** | 0 / 100 / 50 | none |
| Music | `0x04` (4) | 0..8 | 0 / 100 / 50 | Rhythm, Spectrum, Rolling |

The flat `SPEED` byte is 0..100 (default 50). Crossing is the only flat effect capped below 8
colours.

**rgbicv2 effects.** The rgbicv2 "speed" lives in the record itself (the mode-dependent value at
offsets 3-4, plus the movement sub-blocks; see [`ble-protocol-h617a.md`](ble-protocol-h617a.md)
section 6), not in the flat SPEED byte, and runs **0..255** (not 0..100), with effect-specific
floors and defaults:

| Effect | Code | Colour groups (label: min..max) | Speed [min, max, def] (0..255) | Brightness / range | Directions |
|---|---|---|---|---|---|
| Brilliant | 501 | Background: exactly 1; Embellishment: 4..8 | app slider; wire mapping pending | relative-brightness interval 10..100% | none |
| Colorful starry sky | 502 | single: 1..8 | [1, 255, 200] | star size (payload-driven; code fallback 1..25, observed ~1..12); relative brightness on the V1 template | none |
| Colorful meteor | 504 | single: 1..8 | [200, 255, 253] | none | Clockwise, Counterclockwise |
| Colorful meteor shower | 503 | single: 3..8 | [200, 255, 253] | none | Clockwise, Counterclockwise |
| Sparkle | 505 | Embellishment: 1..8; Background: exactly 1 | [200, 245, 240] | relative-brightness interval (0..255) on the V1 template | none |
| Bloom | 506 | Bloom colour: 2..8; Moving colour: 2..8 | none (no speed slider) | relative brightness 1..100% | none shown |
| Stack | 507 | Stack colours: 1..8; Moving colour: 1..8 | n/a (brightness slider instead) | relative brightness 1..100 (default 100) | Clockwise, Counterclockwise |

Notes:

- Current iOS 7.5.21 exposes 2..8 colours in both Bloom groups.
- "Star size" is a type 2 `[max, min]` range carried in the record (confirmed; section 6 of
  [`ble-protocol-h617a.md`](ble-protocol-h617a.md)); the code fallback is 1..25 and the observed
  range was ~1..12.
- Brightness records are template-specific rather than universally scaled by `pct x 2.55`.
  Bloom's single relative-brightness control uses a `0x32` floor and produced
  10/20/30% = `0x45/0x5a/0x6f`. Brilliant exposes a two-handle interval from 10 to 100%.
  Exact Sparkle and Brilliant field mappings remain to be isolated
  ([`ble-protocol-h617a.md`](ble-protocol-h617a.md) section 6).

**Finger Sketch**: freeform paint, no colour-group min/max. **Combo**: one shared flat palette
(up to 8 colours) across up to four chained effects.

> The DIY **Music** family (flat `FAMILY 0x04`, effects Music1..3) is distinct from the app's
> **Music mode** (`33 05 13`; section 3 of [`ble-protocol-h617a.md`](ble-protocol-h617a.md)). The
> DIY Music family reactively drives a user palette over the flat DIY encoding; the app Music
> mode is a separate real-time command that was **not** captured this session (section 5).

## 3. Vibrant (multi-colour gradient)

Vibrant is a client-side gradient capability, not yet implemented. The user picks 2 to 5 colours
and the app interpolates them across all 15 segments, then uploads the resolved per-segment
colours as `0xA3` multi-frames and activates them with `33 05 0a <slot>` (the same mode-`0x0a`
activation as flat DIY and Finger Sketch). Unlike scenes and animated DIY it plays no animation:
it is a static per-segment gradient.

The multi-frame body is `01 <linecount> 03 <header> <15 entries>`, where each entry is
`<segment_index> 01 <R> <G> <B>`. Vibrant reuses the Finger Sketch `TYPE 0x03` encoding (section
2.4): its header begins `03 09 00 ...`, that is Finger Sketch motion `0x09` (Clockwise) with the
speed byte `0x00`. The full byte layout, the observed 14-byte preamble and its open questions are
in [`ble-protocol-h617a.md`](ble-protocol-h617a.md) (section 6). Confirmed by decoding a
red-orange to yellow to green to blue gradient across the segments.

## 4. Scene parameters

(DIY parameters are covered in section 2.)

Scenes that support adjustment carry a `speedInfo.config` (a JSON string in the API). It
describes one or more parameter "pages", each with a set of discrete values selected by an
index. Example (Forest):

```json
[{"color":[237,237,237,250],
  "bright":[{"brightPage":"0","brightValue":[201,216,226,251]}],
  "page":1, "defaultIndex":3}]
```

- `page` = which parameter (a scene can have several).
- `bright.brightValue` / `moveAll` / `color` = the discrete values the slider steps through.
- `defaultIndex` = the default position.

So a scene "speed"/"brightness" slider is not a free 0-100 value; it picks an index into these
arrays. The distilled catalogue keeps this `config` verbatim so we can reproduce the app's
slider steps.

## 5. Capture matrix (what to record next)

Reuse the one-action-per-file loop in [`ble-capture-workflow.md`](ble-capture-workflow.md),
changing one variable per capture. Closed since the last matrix: the app Music mode, the misc
modes (Color Slider, Random Color, Snapshot, Timer), Combo `seqlen` scaling and Video mode (not
offered on the H617A). See [`ble-protocol-open-questions.md`](ble-protocol-open-questions.md) for
the full worklist. What remains here:

| # | Action (in the app)                                  | Confirms                                                        |
|---|------------------------------------------------------|-----------------------------------------------------------------|
| 1 | rgbicv2 Brilliant/Sparkle/Stack: move each slider alone | the concrete per-effect speed-lookup values and the meaning of colour `param1` / `param2` (the record grammar itself is decoded, section 2.3) |
| 2 | rgbicv2 Colorful meteor / meteor shower: change direction | the direction byte and the variant-byte value space        |
| 3 | Colour temperature on the device                     | the corrected true-white frame drives white mode; extend the Kelvin curve |
| 4 | Music, remaining per-mode colour pickers and multi-colour controls | completes the app Music parameter model; Bloom/Shiny style and Fountain direction are closed |

Effect demonstrations (what each effect looks like, for entity naming and previews) are a
separate research task and do not require a capture.

## 6. Tooling

- `tools/ble/fetch_effect_library.py` fetches and distils the scene catalogue for any SKU from
  the public API (no account). Frozen output lives under `tools/ble/catalogues`, and `--check`
  reports API drift without overwriting it.
- `tools/ble/govee-capture.sh` + `tools/ble/decode_govee.py` drive and decode the live BLE
  captures (see [`ble-capture-workflow.md`](ble-capture-workflow.md)).

## 7. Sources

- **Live BLE capture against the device** (definitive for our device): the flat DIY wire format
  and its fixed protocol code (`4`), the flat family/colour/speed limits, the rgbicv2 templates and
  limits, the rgbicv2 **record grammar** (the serialise and parse paths are exact inverses), the
  Brilliant parameter domain, Finger Sketch and the display names were all confirmed on the wire.
  The H617A uses **all four** DIY encodings, chosen per effect: flat (`TYPE 0x04`) for the eight
  animation families, rgbicv2 (`TYPE 0x02`) for the seven rich templates, `TYPE 0x03` for Finger
  Sketch and Vibrant, and `FAMILY 0xFF` for Combo.
- Internal analysis notes (working analysis, not committed): the full record-grammar teardown and
  the speed-lookup model, plus per-effect motion descriptors (confirmed and inferred).
- Govee library API + `scenceParam` -> BLE pipeline: `wez/govee2mqtt` (`src/undoc_api.rs`,
  `src/ble.rs`), `AlgoClaw/Govee` (`decoded/v1.2/explanation_v1.2.md`),
  `Beshelmek/govee_ble_lights` (ships per-SKU catalogues incl. `H619A.json`; `govee_utils.py`
  multi-frame chunker).
- Prior DIY family/style tables (useful cross-check, older `0xA1` generation):
  `egold555/Govee-Reverse-Engineering` (`Products/H6199.md`), `lasswellt/govee-homeassistant`
  (`docs/govee-protocol-reference.md` section 9.5), `ConsciousCode/govee_h7015`,
  `constructorfleet/govee-ultimate`, `Coding-Kiwi/govee-lightbar`.
