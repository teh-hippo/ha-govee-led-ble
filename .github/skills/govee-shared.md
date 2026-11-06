# Govee skills: shared context

Read by `govee-add`, `govee-fix`, `govee-audit` and `govee-resolve`.

## What you have

- **Device evidence.** A private hidden directory, `.reference-material/`, sits beside the main clone (from a worktree, `git rev-parse --path-format=absolute --git-common-dir` gives the clone's `.git`).  Read its README first.  It holds evidence about what Govee devices do and how they are driven, and `map/`, starting-point notes for finding things.  Start from the notes, follow the evidence wherever it leads, and add to the notes anything useful they lacked.
- **Our protocol spec.** `tools/ble/kaitai/` describes the wire; `const.py` profiles, `effect_catalogue.py` and `scene_catalogues/` say what each model exposes.
- **Govee's public scene library**, the feed `tools/ble/refresh_scene_catalogues.py` reads.  Fetching it read-only is fine; it carries fields our catalogue snapshots drop, such as per-scene command versions.
- **Public device pages.** Govee product pages and manuals for physical specs.
- **`CONTRIBUTING.md`** for architecture and non-goals.

## Rules

- The evidence is the truth for how Govee drives its devices.  Where we differ, assume we are wrong unless it can be proven otherwise; recorded device traffic confirms the evidence but does not override it.  If Govee dropped something a device can still do, keep it and flag it.
- Re-derive code and enum maps (music modes, scene types) from the evidence for each model; never copy them from a sibling model or an existing `.ksy`.
- When the evidence shows two paths that disagree (for example two ways Govee drives the same function, sending different frames), don't pick one: report both and flag it for the operator.  The difference may be a deliberate optimisation.
- Keep it private.  Never cite the folder, its files, or how evidence was obtained in the repository, commits, issues, PRs or release notes.  Describe behaviour in your own words and cite public sources only.  Private references belong in the folder's notes.
- Aim for complete support of the device: every control, scene, music mode and effect it offers, except the `CONTRIBUTING.md` non-goals.
- A value copied from a sibling model needs evidence that the two share it.  If a list is supplied by Govee's cloud rather than fixed per model (for example music modes), say so and use the closest evidenced default.
- Report a check as done only if you did it.  For wire behaviour, "matches" means you compared the bytes our builders generate for that model and revision with the bytes the evidence shows.
- Findings outside the task (other models, shared-runtime gaps every model has) are follow-ups: list them; don't widen the change without asking.
- Support status is **Experimental** until an owner confirms it on hardware, then **Supported**.

## Device brief

Used by `govee-add` and `govee-audit`: what the device is and everything it can do, per hardware/firmware revision.
Identity (SKU, BLE name prefixes, Pact type and code, IC count, revisions), physical specs (length, segments, white emitters, mic, camera), and every capability it offers with its BLE contract.

## Workflow for skills that change code

Start in plan mode if the harness has one.  Every plan's task list includes:

1. A code review in a fresh context, however the harness provides one: alignment with the project's goals and structure, no band-aids, no per-model branches unless necessary.  Fix what it finds.
2. Commits, a passing `make check`, and a PR that follows `.github/PULL_REQUEST_TEMPLATE.md`, labelled with the SKU of every model whose behaviour changes.

A fresh checkout needs `make build` before tests or the scene-catalogue refresh tool will run.
