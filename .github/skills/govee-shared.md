# Govee skills: shared context

Read by `govee-add`, `govee-fix`, `govee-audit` and `govee-resolve`.

## What you have

- **Device evidence.** A private hidden directory, `.reference-material/`, sits beside the main clone (from a worktree, `git rev-parse --path-format=absolute --git-common-dir` gives the clone's `.git`).  Read its README first.  It holds evidence about what Govee devices do and how they are driven, and `map/`, starting-point notes for finding things.  Start from the notes, follow the evidence wherever it leads, and add to the notes anything useful they lacked.
- **Our protocol spec.** `tools/ble/kaitai/` describes the wire; `const.py` profiles, `effect_catalogue.py` and `scene_catalogues/` say what each model exposes.
- **Govee's public scene library**, the feed `tools/ble/refresh_scene_catalogues.py` reads.  Fetching it read-only is fine; it carries fields our catalogue snapshots drop, such as per-scene command versions.
- **Public device pages.** Govee product pages and manuals for physical specs.
- **`CONTRIBUTING.md`** for architecture and non-goals.

## Rules

- Use device evidence to establish behaviour, not as an architecture to copy.
  Investigate differences rather than assuming our implementation is correct.
  Reconcile conflicting evidence and recorded traffic against their revision, operating mode and observation context; leave unresolved differences explicit.
  If Govee dropped something a device can still do, keep it and flag it.
- Verify each product's values and enum maps independently.
  Reuse common codecs where the evidence establishes a shared wire shape; do not copy product capabilities or mappings from a sibling or an existing schema without that evidence.
- When the evidence shows two paths that disagree (for example two ways Govee drives the same function, sending different frames), don't pick one: report both and flag it for the operator.  The difference may be a deliberate optimisation.
- Keep it private.  Never cite the folder, its files, or how evidence was obtained in the repository, commits, issues, PRs or release notes.  Describe behaviour in your own words and cite public sources only.  Private references belong in the folder's notes.
- Aim for complete support of the device: every control, scene, music mode and effect it offers, except the `CONTRIBUTING.md` non-goals.
- A value copied from a sibling model needs evidence that the two share it.
  If a list comes from a dynamic service rather than a fixed product contract, preserve that provenance and uncertainty; do not turn an example response into an assumed capability ceiling.
- Report a check as done only if you did it.  For wire behaviour, "matches" means you compared the bytes our builders generate for that model and revision with the bytes the evidence shows.
- Fix shared causes required by the task at their owning layer, including affected callers; a common-runtime defect is not a reason to add a model-local workaround.
  Unrelated findings remain follow-ups; don't widen the change without asking.
- Support status is **Experimental** until an owner confirms it on hardware, then **Supported**.

## Device brief

Used by `govee-add` and `govee-audit`: what the device is and everything it can do, per hardware/firmware revision.
Identity (SKU, BLE name prefixes, Pact type and code, IC count, revisions), physical specs (length, segments, white emitters, mic, camera), and every capability it offers with its BLE contract.

## Workflow for skills that change code

Start in plan mode if the harness has one.
Follow the architecture and change/test-design rules in `CONTRIBUTING.md`; do not maintain a second set of device-specific exceptions here.
Every plan's task list includes:

1. Trace the affected contract end to end and compare equivalent existing paths.
   Classify proposed differences as declarations, wire formats, genuinely distinct semantics or shared defects before choosing a change.
2. Choose the smallest fix at the owning layer, using existing capability and override seams.
   Identify any duplicate paths or state it replaces, and justify any new execution path.
3. Validate through existing shared suites, preserving evidenced device behaviour without preserving integration bugs.
   Add coverage only for distinct contracts or safety invariants, not a separate suite for each device or report.
4. A code review in a fresh context, however the harness provides one: challenge both remaining special treatment and unnecessary abstraction, check affected callers and deletion of superseded code, and fix supported findings.
5. Commits, a passing `make check`, and a PR that follows `.github/PULL_REQUEST_TEMPLATE.md`, labelled with the SKU of every model whose behaviour changes.

Keep implementation and review scoped by root cause.
Do not turn every audit observation into its own issue, test module or permanent instruction.

A fresh checkout needs `make build` before tests or the scene-catalogue refresh tool will run.
Follow `CONTRIBUTING.md` for release policy.
Merged release-bearing work publishes a master prerelease automatically; stable publication is the operator's manual decision.
