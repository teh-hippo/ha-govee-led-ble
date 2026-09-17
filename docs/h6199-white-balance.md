# H6199 White Balance

The generated Kaitai reply owns all six register fields: device-default
flag/red/blue and current flag/red/blue. Coordinator snapshots and durable
recovery preserve all six. Flags 0 (auto) and 1 (manual) are writable; other
reported byte values remain lossless, decode-only state.

Explicit profile authoring, including Live preview, intentionally selects
manual mode. Verification compares the mode flag as well as both gains.
`apply_white_balance(coordinator, None)` resets to freshly read device defaults,
not the profile calibration table's neutral position. Defaults cannot be
written independently, and a changed default tuple prevents recovery from
claiming a complete match. H6099's scalar writer is unchanged.

Legacy recovery snapshots without a flag retain `None`. A later read cannot
reconstruct the original mode, so unsafe WB restoration is skipped and recovery
remains uncertain. Restored values never advance observation revisions.

Live cancellation stops pending writes; it does not roll back the light, as
before this fix. Profile/template defaults are authored settings, not device
factory defaults. No new reset UI or automatic preview rollback is introduced.

`tests/test_h6199_white_balance.py` replays the captured same-gain auto/manual
frames and checks recovery, persistence, reset, legacy state, and verification.
These are software regressions, not a new physical-device qualification.
