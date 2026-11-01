# Govee skills: shared method

Used by `govee-fix`, `govee-add` and `govee-audit`.  These skills find gaps in our approach, for planning or implementation.  They are read-only: write session artifacts, not tracked files, and do not run generators or `make check`.  Invocation alone authorises neither implementation nor publication.

## Terms

Use these exactly: **Experimental** (awaiting owner confirmation on hardware) and **Supported** (owner-confirmed).  `speculative/` Kaitai holds unconfirmed wire hypotheses and is separate from support status.

## Ground rules

- Resolve exact SKUs from attributable evidence; clarify conflicting identity instead of guessing.  Keep owners, revisions, environments and reported versus checkout versions separate.
- Follow `CONTRIBUTING.md` (architecture, non-goals).  Target full in-scope support across hardware and firmware revisions: enable every defensible capability backed by exact-model evidence or speculative Kaitai, keep only disproven or unsafe paths disabled, and preserve unknowns rather than inventing facts.
- Kaitai (`tools/ble/kaitai/`) is the protocol documentation.  Read the model's `.ksy` schemas first; a wire fix belongs there, not in handwritten offsets.
- Treat reported causes and workarounds as hypotheses.  Do not weaken confirmation, add retries or copy another SKU's fix without evidence.
- Ask whether a major gap belongs in the current issue/PR or a follow-up, and before materially changing the approach.  Keep deferred findings visible.

## Reference material (the Android app)

Locate the main clone with `git rev-parse --path-format=absolute --git-common-dir`; read `.reference-material/README.md` in its parent and follow its confidentiality and lookup rules.  It gives starting points, not coverage limits: look for what a lookup did not cover.
Use the LSP for symbols and references in large Python and Java files and for Markdown/YAML outlines; read ranges, not whole files.  Read each large file once and reuse what you learned.  Use `python3` for stdlib JSON/ZIP inspection.

## Trace

Connection/subscription -> identity admission -> request construction -> framing/transformation -> physical write -> replies -> parsing -> state -> verification.
Find the last successful stage and the first evidenced divergence; a service error does not prove a malformed command.
Compare observed TX/RX with generated output at the same layer, keeping source/version, direction, revision, sequence and timing.  Distinguish captured, reconstructed and builder-generated frames.
Separate wrong bytes or routing from transport failure, unanswered queries, transitional readback and wrong confirmation expectations.  Accepted writes, visible rendering, fresh observations and optimistic state are not interchangeable.

## Surface to audit for a model

Map `(pact_type, pact_code, hardware, firmware, subordinate_20/21)` to capabilities independently, across `.ksy`, `const.py`, `effect_catalogue.py`, exact-SKU scene catalogues and the shared adapter, coordinator and entity paths.
Check product IDs/remapping, BLE names, encryption, geometry, white emitters and power limits against attributable evidence.

| Surface | Check |
| --- | --- |
| Power, brightness | Register bounds and rescaling, clamping, non-zero readback |
| RGB, Kelvin, segments | Selectors, bounds, direct/companion RGB, mask width, whole versus partial writes, fresh geometry |
| Scenes | Exact-SKU catalogue, selector eligibility, body routing, activation, speed defaults |
| Music | Mode IDs, parameter bounds, companion bodies, upload ordering, ACK policy |
| DIY, Workshop | Body allowlists, rate/palette/layer bounds, upload ACKs, slot safety, restoration |
| Settings, video, DreamView | Control eligibility, boolean/enum semantics, query/write behaviour, group capacity |

Catalogue type, body family and wire subtype are independent.  Upload ACKs are separate from status readback; query silence proves neither ACK policy nor cause.
Flag handwritten offsets or command literals, model branches, and static profiles that bypass the effective `device_profile()`.
For each field: named field -> observation -> sibling preservation -> recovery -> generated write -> fresh verification.  Classify it applied, preserved, decode-only or unknown.

## Output

Four sections, as in `.github/PULL_REQUEST_TEMPLATE.md`: request and known context; research findings; candidate support scope; model-specific changes and owner checks.
Defer only checks needing unavailable evidence, implementation or hardware, and state the next discriminating check.  Keep planned checks distinct from performed ones.  If no correction is justified, report the competing explanations.
Keep evidence, attributable frames, paths and decisions in `<session_folder>/files/<skill>-<model>.md`, append to it instead of re-reading it, and link it from the plan.
Report unexamined, investigated-but-unresolved and not-hardware-qualified paths separately.  Claim alignment only when coverage is complete, and report only checks you performed.
A release candidate can be built for hardware testing (`docs/release-candidates.md`); recommend one when a hardware result is the next discriminating check, but do not build or publish it without approval.
