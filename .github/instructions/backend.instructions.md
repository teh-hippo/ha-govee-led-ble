---
applyTo: "custom_components/**/*.py,tests/**/*.py"
---

Keep `CONTRIBUTING.md` as the architectural and acceptance authority.
Trace shared callers before adding an override, and put protocol structure only in `.ksy`.
Never select shared execution by an exact SKU.  Use typed semantic declarations or declared grammars, and keep every capability flag to one exact contract across all profiles.
If a new product requires scattered common-code branches, fix the missing shared boundary rather than adding a snowflake path.
Use the narrowest existing pytest file while iterating; use xdist through `make check-tests` rather than starting parallel pytest processes.
Preserve asynchronous ownership, acknowledgement-driven completion and recovery boundaries.
Use `make check-fast` after broad backend work and `make check` at completion.
