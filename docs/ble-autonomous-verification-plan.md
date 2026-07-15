# Autonomous iPhone-driven BLE verification plan

## Objective

Verify the supported Govee protocol end to end by predicting each BLE transaction from the
integration, performing the corresponding action in Govee Home on the iPhone, observing the
actual Bluetooth traffic, checking device state, and restoring Home Assistant ownership.

The first tranche covers power, colour, music, and built-in scenes. Work stops after those runs
for owner review. No live verification in this plan begins without explicit approval.

## Verification contract

Every live run must establish four independent facts:

1. **Prediction:** exact TX bytes or an explicitly bounded structural prediction are frozen before
   the phone action.
2. **App action:** the dedicated phone operator performs one approved action through CoreDevice
   HID.
3. **Wire observation:** the marked pcap contains the attributable app TX frame and any device RX
   acknowledgement or status.
4. **Restoration:** the exact baseline is restored, Govee Home releases the BLE link, and the Home
   Assistant config entry is loaded and available.

A changed screen or visible animation is supporting evidence only. It cannot replace BLE
observation or state read-back.

## Roles and context isolation

- The main verification agent owns predictions, decoded bytes, evidence classification, Home
  Assistant hand-off, and the campaign ledger.
- GPT-5.6 Terra owns every phone command and visual interpretation. It returns text findings only.
- Full screenshots and pcaps remain local. The main conversation receives no image attachments.
- One operator owns a run from its first marker through restoration. Do not split a live run across
  agents.

For every marker, Terra returns:

- viewer health and unlocked state;
- target device identity and current navigation path;
- control label and displayed value before the touch;
- touch coordinates, timestamp, and wait duration;
- displayed value after the touch;
- `confirmed` or `ambiguous`.

An ambiguous visual result invalidates the action window even if a plausible BLE frame appears.

## Safety gates

- Target only the designated H617A Cupboard Skirt device.
- Never touch the other H617A device.
- Keep H617A master brightness at 5%, and never above 10%.
- Home Assistant owns the BLE link between runs.
- Disable and reload only the target config entry. Do not restart Home Assistant.
- Use one persistent, loopback-only CoreDevice viewer per run.
- Bind decoded frames to the target Bluetooth connection handle and address. Fail if another Govee
  connection contributes frames to the action window.
- Persist run phase, baseline, target entry, and prediction hash after every marker.
- Keep each live window below 90 seconds and maintain phone activity at least every 60 seconds.
- Stop on any unexpected frame, ambiguous target, lost baseline, phone lock, or failed restoration.
- H6199 remains app-sniff only and requires fresh approval before any state-changing run.

If the phone locks, CoreDevice disconnects, the main process crashes, or recovery requires a
Developer Disk Image remount, the run is invalid. Preserve its artifacts, assign a new run ID,
recover Home Assistant ownership, reassert the baseline, and start again. Never append post-recovery
actions to the original capture.

## Campaign baseline

The H617A baseline for the first tranche is:

| Field | Value |
| --- | --- |
| Power | On |
| Master brightness | 5% |
| Mode | Built-in scene |
| Scene | Sunrise, code `0x0000` |
| Home Assistant | Config entry loaded and entity available |

Confirm the baseline immediately before every hand-off. Restore Sunrise at 5% in the app before
returning the link to Home Assistant. If the observed state differs before a run, stop and record
the new baseline rather than silently normalising it.

The restoration packet set is frozen for every run:

```text
Sunrise:      3305040000000000000000000000000000000032
Brightness 5: 3304050000000000000000000000000000000032
```

Both commands must be observed or an equivalent already-correct state must be proven by read-back.
Do not rely on power-on memory to preserve brightness.

## Prediction source

For each run:

1. Generate packets from the commit under test using `protocol.py`.
2. Independently compare field meanings with the formal protocol reference.
3. Store the exact predicted hex in the run record before the first touch.
4. Hash the prediction JSON with SHA-256 and record the digest in capture metadata before start.
5. Do not alter the prediction after seeing the capture. A mismatch remains a mismatch.

Known status queries:

```text
Power:       aa010000000000000000000000000000000000ab
Colour mode: aa050000000000000000000000000000000000af
```

The app may not issue a colour-mode query in every action window. Exact app TX is mandatory.
Device state is confirmed from an attributable RX status when present, otherwise through the
integration after Home Assistant regains the link.

## Safe runner

Do not run `tools/ble/validate_protocol.py --live` unchanged. Its current plan combines many
actions into a long session and includes 100% brightness steps, which violate this campaign's
bounded-run and brightness rules.

`tools/ble/safe_verify.py` implements the required one-run manifest. It:

- executes one approved run at a time;
- records predicted TX and expected RX before the action;
- accepts timestamped `armed`, `before-action`, `after-action`, and `settled` markers;
- binds frames to the target Bluetooth connection handle and address;
- fails on missing, duplicate, or unexpected matching TX frames;
- reports extra Govee writes in the action window;
- aborts on any brightness command or status above 10%;
- records and verifies the prediction hash;
- supports a restoration packet set and Home Assistant availability check;
- persists a crash-recovery state file after every marker;
- writes JSON and Markdown evidence without embedding screenshots;
- passes replay and simulation tests before phone use.

The runner also binds the prediction digest to `govee-capture.sh` active state and final metadata,
cross-checks `.actions.tsv` against persisted markers, records run provenance, and produces
terminal invalid evidence after successful recovery.

The harness is an orchestrator, not a UI oracle. It must not decide phone coordinates or infer
whether the intended control was selected. Terra performs and reports that decision.

## Operator manifest and action windows

Each run manifest contains private, uncommitted target identity:

- expected Bluetooth address and local name;
- device-card label and stable visual anchors;
- exact app navigation path;
- control label, expected displayed value, and calibrated coordinates;
- maximum wait and expected number of matching frames.

Ownership checks are part of `armed`:

1. Home Assistant reports the target entry loaded and available before hand-off.
2. Disabling the entry moves it to `not_loaded` with `disabled_by=user`.
3. Govee Home reports the private target identity connected.
4. The pcap maps the active connection handle to that target address.
5. More than one candidate Govee connection invalidates the run.

The committed plan identifies catalogue paths:

- Colour > exact primary red or blue control;
- Music > Rhythm > Dynamic or Calm;
- Scene > Festival > Candlelight;
- Scene > Festival > Halloween;
- Scene > Natural > Sunrise for restoration.

Before a colour run, Terra must confirm that the selected controls represent exact
`#FF0000` and `#0000FF`. If the current app does not expose exact values or a previously proven
control, stop and replace the prediction before capture. Do not treat a visually red or blue chip as
an exact RGB oracle.

Each action uses a bounded window:

1. `armed`: prediction hash, baseline, target identity, and viewer health are frozen.
2. `before-action`: decoder buffer is drained and the control's current label or value is recorded.
3. Touch the control once.
4. Wait three seconds while retaining all target-connection frames.
5. `after-action`: record the displayed state and the final frame timestamp.
6. `settled`: require no additional matching TX frame for two seconds.

Preparation writes, action writes, and restoration writes use separate windows. A delayed frame
crossing a window boundary invalidates the run rather than being reassigned.

## Interrupted-run recovery

The persisted state file is the source of truth after a crash, lock, or tool failure. Recovery is
not a continuation of the failed run.

1. Preserve the existing pcap, markers, prediction, and state file.
2. Stop the capture logger and persistent viewer by their recorded identifiers.
3. If the phone is locked, obtain an owner unlock before issuing another phone command.
4. Recover CoreDevice services only after the viewer is stopped.
5. Terminate Govee Home cleanly and enable the target Home Assistant entry.
6. Reload the entry. If it remains unreachable, use the proven connect, back-out, terminate,
   enable, and reload hand-back sequence.
7. Reassert Sunrise and brightness 5%, then confirm the entry is loaded and available.
8. Mark the failed run `invalid`, clear the recovery state, and create a new run ID.

## First tranche

| Run | Target | App sequence | Required result |
| --- | --- | --- | --- |
| 1 | Power | Sunrise on -> off -> on | Exact off and on commands; power status follows; Sunrise and 5% remain intact. |
| 2 | Whole-strip colour | Red -> blue -> red, then restore Sunrise | Exact `33 05 15 01` frames with mask `0x7FFF`; static status agrees. |
| 3 | Music | Rhythm Dynamic -> Calm -> Dynamic, then restore Sunrise | Exact mode `0x03`, sensitivity `99`, with only the style byte changing. |
| 4 | Simple built-in scene | Candlelight, then restore Sunrise | Exact simple scene activations, no A3 upload. |
| 5 | Multi-frame built-in scene | Halloween, then restore Sunrise | Exact three-part A3 body, type `0x01`, activation code `1173`, then Sunrise restoration. |

Stop after run 5. Present the evidence matrix and all mismatches to the owner before planning or
executing the next live tranche.

## Run 1: power

**Task ID:** `h617a-verify-power`

Predicted app TX:

```text
Power off: 3301000000000000000000000000000000000032
Power on:  3301010000000000000000000000000000000033
```

Predicted status when queried:

```text
Off: aa010000000000000000000000000000000000ab
On:  aa010100000000000000000000000000000000aa
```

Procedure:

1. Confirm Sunrise, on, 5%, and Home Assistant availability.
2. Hand the link to Govee Home and start the marked capture.
3. Mark and tap power off.
4. Wait for the command and power status.
5. Mark and tap power on.
6. In the restoration window, reassert Sunrise and brightness 5% if read-back does not already
   prove both values.
7. Close the app, return the link to Home Assistant, and confirm the same baseline.

Pass only if both TX frames are exact and no mode, colour, or brightness write appears in either
power action window. Restoration writes are assessed in their separate window.

## Run 2: whole-strip colour

**Task ID:** `h617a-verify-colour`

Predicted app TX:

```text
Red:  33051501ff00000000000000ff7f00000000005d
Blue: 330515010000ff0000000000ff7f00000000005d
```

Predicted restoration TX:

```text
Sunrise:      3305040000000000000000000000000000000032
Brightness 5: 3304050000000000000000000000000000000032
```

Predicted colour-mode status when queried:

```text
Red:  aa051501ff000000000000000000000000000044
Blue: aa0515010000ff00000000000000000000000044
```

Procedure:

1. Confirm the campaign baseline and hand off the link.
2. Confirm the exact red control reports `#FF0000`, then mark and tap it.
3. Confirm the exact blue control reports `#0000FF`, then mark and tap it.
4. Mark and tap red again to prove A/B/A attribution.
5. Restore Sunrise and brightness 5% in a separate window.
6. Return the link to Home Assistant and verify availability.

Pass only if the mask bytes are `FF 7F`, the RGB bytes are exact, red reproduces byte-for-byte,
and no per-segment or colour-temperature frame is substituted.

## Run 3: music

**Task ID:** `h617a-verify-music-rhythm`

Use Rhythm with sensitivity 99 and automatic colour. This classic mode avoids an extended A3
parameter body, so the first music check isolates the base command.

Predicted app TX:

```text
Dynamic: 3305130363000000000000000000000000000045
Calm:    3305130363010000000000000000000000000044
```

Predicted restoration TX:

```text
Sunrise:      3305040000000000000000000000000000000032
Brightness 5: 3304050000000000000000000000000000000032
```

Predicted colour-mode status when queried:

```text
Dynamic: aa051303630000000000000000000000000000dc
Calm:    aa051303630100000000000000000000000000dd
```

Procedure:

1. Confirm the campaign baseline and hand off the link.
2. In a preparation window, set Rhythm to sensitivity 99, automatic colour, and Dynamic.
3. Confirm all three values in the app and, when available, an attributable status. If the current
   screen cannot prove the complete setup, invalidate the run.
4. Restore Sunrise, then start a new action window.
5. Select Rhythm. The expected activation is the frozen Dynamic frame.
6. Mark and select Calm.
7. Mark and restore Dynamic.
8. Restore Sunrise and brightness 5% in a separate window.
9. Return the link to Home Assistant and verify availability.

Pass only if mode remains `0x03`, sensitivity remains `0x63`, and byte 5 is the sole semantic
change between Dynamic and Calm. The frame must contain no manual-colour count or RGB payload.

## Run 4: simple built-in scene

**Task ID:** `h617a-verify-scene-candlelight`

**Navigation path:** Scene > Festival > Candlelight.

Predicted app TX:

```text
Candlelight: 330504090000000000000000000000000000003b
Sunrise:     3305040000000000000000000000000000000032
Brightness 5: 3304050000000000000000000000000000000032
```

Predicted colour-mode status when queried:

```text
Candlelight: aa050409000000000000000000000000000000a2
Sunrise:     aa050400000000000000000000000000000000ab
```

Pass only if Candlelight uses a single activation command with code `0x0009`, no A3 frame appears
in its action window, and Sunrise plus brightness restoration is exact.

## Run 5: multi-frame built-in scene

**Task ID:** `h617a-verify-scene-halloween`

Halloween is selected because it verifies a complex catalogue payload and the non-default scene
type `0x01`.

**Navigation path:** Scene > Festival > Halloween.

Predicted app TX, in order:

```text
a3000103018306fff5000500ffffff0500ffe9c6
a301ff0500ffffff0500ffe9d90500fff8ff0696
a3ff0004ff1e00ff5a00ff3200ff780000000056
33050495040000000000000000000000000000a3
```

Restoration:

```text
Sunrise:      3305040000000000000000000000000000000032
Brightness 5: 3304050000000000000000000000000000000032
```

Predicted colour-mode status when queried:

```text
Halloween: aa0504950400000000000000000000000000003a
Sunrise:   aa050400000000000000000000000000000000ab
```

Pass only if all A3 chunks are present once and in order, the final activation code is `1173`
little-endian, the scene type is represented by the uploaded type `0x01` body, and Sunrise
plus brightness restoration is exact.

## Evidence record

Each run produces:

- `<timestamp>-<taskid>-<focus>.pcap`;
- `.actions.tsv` and `.meta.json`;
- a prediction JSON and SHA-256 digest written before the action;
- decoded TX and RX frames;
- target connection address and handle;
- Terra's text-only operator record for every marker;
- a wire-pass, TX-only pass, mismatch, no-write, invalid, or unresolved verdict;
- the exact restoration result;
- Home Assistant entry state before and after;
- persisted recovery state cleared only after successful hand-back;
- the integration commit, app build, device firmware, and catalogue hash.

The summary table must distinguish:

| Result | Meaning |
| --- | --- |
| Wire pass | Exact TX, attributable device RX, UI state, and restoration agree. |
| TX-only pass | Exact TX and restoration agree, but state was confirmed only after Home Assistant hand-back. This does not validate the RX parser. |
| Mismatch | An attributable app frame differs from the frozen prediction. |
| No write | The app action produced no attributable command. |
| Invalid | Target binding, phone state, timing window, brightness guard, or recovery boundary failed. |
| Unresolved | The intended control, reply, device state, or restoration remains ambiguous. |

Never convert a mismatch to Pass by editing the prediction after capture.

## Campaign after owner review

After the first tranche is reviewed, continue in this order:

1. **H617A core state:** brightness at 1%, 5%, and 10%; warm, middle, and cool colour temperature;
   firmware, hardware, brightness, power, and colour-mode queries.
2. **H617A segments:** one segment, all segments, per-segment brightness, segment painting, and
   capture of the exact request that elicits each `AA A5` reply group.
3. **H617A scene coverage:** one type-`0x02` multi-frame scene, offline generation of all 83 frozen
   variants, catalogue drift checks, a test that rejects scene codes incompatible with the current
   parser's trailing-zero rule, and one adjustable-scene parameter if an editor path exists.
4. **H617A custom effects:** one bounded run each for Flat, Finger Sketch, Vibrant, Combo, each
   rgbicv2 target, and each remaining Workshop field family.
5. **H617A music depth:** all 11 mode IDs and every exposed style, colour, count, speed, direction,
   gradient, and relative-brightness control. Offline tests must also retain palette-length
   rejection and protection for volatile Separation and Piano Keys offsets.
6. **H617A timers:** scheduled slots, sleep, wake-up, repeat days, and explicit confirmation that
   gradual and power-off memory are absent from the current app surface. Unsupported experimental
   builders must remain explicitly experimental or be removed; absence from the app is not builder
   validation.
7. **H6199 app-sniff campaign:** only after fresh approval, beginning with power, brightness, RGB,
   colour temperature, full video frames, four music modes, and read-back. Scene transport requires
   separate simple and A3 runs. Segment writes, DIY, white balance, and advanced `0xA9` controls
   remain separate gated runs.
8. **Offline parser resilience:** firmware and hardware selector failures, null-terminated version
   strings, malformed payloads, prediction hash validation, and target-connection filtering.

Each item remains one scene or one tightly related control family per run.

## Completion gate

Verification is complete only when:

- every supported public builder and parser has attributable evidence at its declared model scope;
- every exposed Home Assistant capability is validated for that model or disabled;
- every frozen catalogue row has a terminal classification;
- all prediction manifests pass replay and simulation;
- all target-binding, brightness, hash, crash-recovery, and negative-path guards pass;
- every live mismatch has a resolved code, capability, or documentation disposition;
- unsupported experimental helpers are either retained with an explicit non-production scope or
  removed;
- Home Assistant ownership and the exact device baseline are restored after every run;
- the owner and expert panel approve the final evidence matrix.

## Expert review outcome

Three independent reviews regenerated the first-tranche packets and found them byte-identical to
the current builders and frozen catalogue. They also required the following before execution:

- address-bound decoding rather than packet-signature filtering alone;
- persisted crash recovery and run invalidation;
- an enforced 10% brightness ceiling;
- immutable prediction hashes;
- exact navigation and control manifests;
- bounded marker windows with delayed-frame detection;
- explicit Sunrise and 5% restoration;
- distinct wire-pass and TX-only verdicts;
- separate positive live coverage and offline negative-path tests.

These requirements are incorporated above and implemented by the safe runner and its replay and
simulation tests. Live execution remains owner-approval gated one run at a time.
