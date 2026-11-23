---
applyTo: "frontend/**"
---

Use `npm --prefix frontend run dev` with the existing Vite fixtures for local editor iteration.
Run `npm --prefix frontend run typecheck` and `npm --prefix frontend run test:unit` while editing.
Run mobile WebKit browser tests through `make check`; Playwright owns its Vite server and port.
When an imported backend contract changes, update `effect_contracts.py` and `frontend/src/contracts.ts`, then run `make fixtures`.
