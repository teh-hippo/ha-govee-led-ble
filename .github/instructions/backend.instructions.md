---
applyTo: "custom_components/**/*.py,tests/**/*.py"
---

Keep `CONTRIBUTING.md` as the architectural and acceptance authority.
Trace shared callers before adding an override, and put protocol structure only in `.ksy`.
Use the narrowest existing pytest file while iterating; use xdist through `make check-tests` rather than starting parallel pytest processes.
Preserve asynchronous ownership, acknowledgement-driven completion and recovery boundaries.
Use `make check-fast` after broad backend work and `make check` at completion.
