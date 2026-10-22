# Speculative protocol schemas

This directory contains exact-model protocol hypotheses for `Experimental`
candidates and `Supported` models whose wire paths are derived from APK or
protocol analysis rather than official-app BLE captures.  New model candidates
and speculative Kaitai schemas can merge directly to `master` once `make check`
passes, without a blocking prerelease gate.  Follow the speculative-schema and
capture-promotion rules in [`CONTRIBUTING.md`](../../../../CONTRIBUTING.md).

Known compatibility aliases that do not justify copied schemas:

| Model | Current hypothesis | Status |
| --- | --- | --- |
| H617E | H617A-compatible wire behaviour | Supported; shares H617A wire grammar pending exact-model captures |
| H6076 | H617A-like basic control and state paths; submode `0x0f` music selector with A3 companions | Supported; basic controls and revision-gated music selector use shared/speculative schemas |
| H6102 | 20-byte `0x33` power, brightness, and `0x15/0x01` RGB layouts | Supported; revision-gated capabilities resolved per Pact and firmware/hardware identity |

Official scene catalogue availability is separate from protocol evidence.  Use
the exact-SKU catalogue fetcher, but do not infer transport, activation, or
readback compatibility from catalogue contents.
