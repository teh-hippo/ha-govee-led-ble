# Govee model evidence

[CONTRIBUTING](../../CONTRIBUTING.md) owns scope, architecture and acceptance.
[Release candidates](../../docs/release-candidates.md) owns publication and qualification.

## Find the active route

Record the checkout SHA privately with the requested operation and known SKU, Pact, hardware and firmware.
Include that revision in the report only when the result is revision-specific or needs a reproducible pin.
Check for exact-SKU reports and read the confirmation thread when available, including the latest owner retest.
Separate what worked, what failed and what was missing on each reported version.
Use the exact-SKU brief in the maintainer-provided evidence workspace when available; the index, captures, profile and active callers are other entry points.
If private evidence is unavailable, use available public evidence and record the resulting limits.
Keep private references in private notes; describe behaviour in original wording in public material.

Trace the selected revision and operation from public control through profile, catalogue or codec to preparation, transport, observation and recovery as applicable.
Trace required observations back to the connection or preceding action.
For a temporary safety refusal, check that the guard blocks the operation without its prerequisite and allows it once the prerequisite is met.
Check registry precedence, overrides and fallback callers when they can select a different route.
Use indexed routes to save navigation, and recheck their scope and freshness when the conclusion depends on them.
Use symbol navigation when available; bounded search and file reads also work.

For a whole device, classify discovery/identity, physical and logical geometry, ordinary controls, status, settings, scenes, music, DIY and other effects, and recovery.
Include applicable entry points, revision boundaries, and evidenced missing or gated capabilities.
Choose representative operations by the route they actually take, including different prerequisites or encodings behind the same control.
For a targeted report, follow the affected contract across equivalent callers and profiles.

## Maintain the evidence ledger

Maintain a claim ledger before evaluating or reporting any material result.
Every claim that can affect a conclusion requires a row with:

- the operation, exact SKU and complete revision tuple (Pact type and code, firmware, hardware, and any other relevant revision marker);
- the exact source and revision provenance, including capture/thread/reference location, observation or retrieval date, and the checkout or release where code evidence was checked;
- source reachability: a durable public reference, public but revision-limited reference, private maintainer evidence, or unavailable source;
- its authority class;
- the inspected Home Assistant public entry points and route result, explicitly recording absence or the blocking point; when an executable route exists, its terminal handoff at admission, a writer, acknowledgement, observation or recovery;
- the expected result and observed result in the same operation and revision context;
- the freshness check, its date and whether it passed;
- its disposition: match, software defect, missing support, evidence conflict, policy/non-goal or unchecked.

Mark unavailable revision fields explicitly; never fill them by inference from another SKU or Pact.
Do not combine claims from unlike revision tuples.

Use exactly one of these authority classes for the evidentiary source:

- **exact owner observation:** the owner reports a result for the stated SKU and complete revision;
- **capture:** independently inspectable bytes or diagnostics attributable to that revision;
- **independent public reference:** a publicly reachable source not authored by this integration;
- **profile declaration:** a repository product claim or capability declaration;
- **KSY structural authority:** a supported Kaitai schema's field layout or codec structure;
- **speculative KSY hypothesis/comment:** an unqualified parser placement, value interpretation or comment under `speculative/`;
- **generated mirror:** generated protocol output derived from Kaitai;
- **active runtime:** the currently selected public product path, profile and codec execution.

Authority classes are not interchangeable.
An owner observation establishes a reported product result, a capture establishes only its inspectable bytes, and active runtime establishes software reachability rather than physical acceptance.
KSY structure establishes wire layout, not valid product bounds or supported operations.
Exact-SKU evidence does not establish behaviour for a shared-codec neighbour, and shared-codec inference does not establish exact-SKU physical behaviour.
Generated output is non-authoritative until the Kaitai input is fresh and the ignored local runtime mirror has passed the non-mutating `make verify-protocol-fresh` check; regeneration source authority remains with Kaitai.
Public reachability records whether another reviewer can inspect the source, not whether a software operation is reachable.

For public reachability, inspect the offered Home Assistant entities, services, Studio actions and other applicable public entry points.
Record both absent routes and routes blocked before execution as evidence of missing supported behaviour; do not invent a terminal handoff where no route exists.
When a route exists, trace it through admission and name its last proven terminal handoff.
Public availability of a control or successful handoff to a writer does not prove acknowledgement, physical acceptance or independent readback.

## Establish and report the result

- **Basis:** exact capture or owner observation, active exact route, demonstrated shared route, public reference or inference.
  A catalogue entry, profile flag or passing codec test does not establish what Home Assistant offers or executes.
  Public specifications do not prove wire behaviour.
  A permanent capability exclusion needs independent product evidence or [project policy](../../CONTRIBUTING.md#repository-non-goals) to justify it.
  A declared profile fact, its owner confirmation and a runtime observation are separate authorities; do not merge one into another.
  A diagnostic or cached value does not invalidate an independently declared and owner-confirmed product fact.
- **Disposition:** confirmed match, defect, gap, conflict, policy/non-goal or unchecked.
  A defect needs an established contract and a demonstrated divergence in the same context.
  Software proof can establish a software defect; it does not qualify physical behaviour.
  A standalone audit does not require live execution; physical qualification belongs to the [release-candidate runbook](../../docs/release-candidates.md).
  An internal evidence marker or speculative parser location records uncertainty at that boundary; it is not itself a user-visible finding.
  Record credible alternatives and the revision, caller or observation that would distinguish them.
- **Impact:** rank reachable user consequences separately from evidence strength.
  Missing evidence or prerequisites are unchecked, not unsupported.

For each material result, give the operation, active evidence and observed result.
Name the affected user operation and its consequence before describing protocol bytes, ACKs or codec labels.
Before assigning severity, cross-check the final report against the ledger:
each finding must identify its row, use the same SKU and revision provenance, and record the inspected public entry points and route result; require a terminal handoff only when a route exists.
Keep authority, expected result and disposition distinct.
Remove unledgered claims, downgrade unreconciled revision or route claims to unchecked, and resolve any stale generated mirror before using it.
Omit generic audit-method caveats when they do not affect a material result.
Never report unperformed live BLE operation or physical qualification as an audit finding, gap, severity or limitation.
Do not downgrade or require requalification of owner-confirmed Supported models solely because of internal evidence annotations or synthetic-test limitations.
Compare generated bytes with independent expected bytes before claiming a wire match.
Record exact-model discoveries in the evidence workspace when updates are in scope; suggest them in a read-only report otherwise.
