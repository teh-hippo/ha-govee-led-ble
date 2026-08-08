# Offline pause gate

Phase 1 pauses until all items are present.

- [x] Offline suite passes with plugin autoload disabled.
- [x] TCP and UDP egress guards prove non-loopback access is rejected.
- [x] Python and OpenSSL versions recorded.
- [x] Device-facing TLS negotiates TLS 1.2 / `AES256-SHA256`.
- [x] ECDSA and wrong-host certificates are rejected.
- [x] Exact fabricated upstream request bytes reviewed.
- [x] Six retry requests produce one upstream call.
- [x] Identity, chunked and gzip payload-identity proofs pass.
- [x] Gzip JSON schema extraction is separately proven.
- [x] Events, logs, tracebacks, argv, environment and generated evidence pass the fabricated-secret scan.
- [x] Cached and rendered bytearrays use best-effort zeroing; residual memory risk is documented.
- [x] Unapplied isolation manifest generated and validated.
- [x] Threat model complete.
- [x] Exact Run A and restore runbooks complete.
- [x] Observed request fingerprint and its missing fields are documented.
- [x] File/process inventory complete with permissions.
- [x] 503 control fingerprint recorded: six attempts, about 2.1 seconds apart, about 11.6 seconds total.
- [x] Public repository `git status --porcelain` is empty.
- [x] Public `pyproject.toml` and `uv.lock` are unchanged.
- [x] One Opus 5 Phase 1 review and one final live-readiness review completed; blocking
  orchestration findings were fixed.
- [x] User reviewed and approved progression beyond the offline pause.
- [x] Real UniFi apply/status/teardown rehearsal passed without device access.
- [x] AI-lab swap-off/restart/restore rehearsal passed.
- [x] Live-host DNS, NTP, TLS and production-TLS-prewarm checks passed without production HTTP.
- [x] Version canaries were captured and matched after restore. The user explicitly accepted
  repairing any calibration reset in the Govee app instead of requiring photographs or an
  ordinary power-cycle proof.
