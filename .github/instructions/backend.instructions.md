---
applyTo: "custom_components/**/*.py,tests/**/*.py"
---

Use the [shared architecture](../../CONTRIBUTING.md#architecture) and [test guidance](../../CONTRIBUTING.md#development).
Trace affected callers and preserve ownership, completion and recovery boundaries.
Use the narrowest existing pytest target while iterating; use the configured workers instead of parallel pytest processes in one checkout.
