# Speculative protocol schemas

This directory contains exact-model hypotheses for Experimental, Partial, and
Compatible support.  Follow the speculative-schema and promotion rules in
[`CONTRIBUTING.md`](../../../../CONTRIBUTING.md).

Known compatibility aliases that do not justify copied schemas:

| Model | Current hypothesis | Status |
| --- | --- | --- |
| H617E | H617A-compatible wire behaviour | Compatible pending exact-model evidence |
| H6076 | H617A-like basic control and state paths | Partial; all other capabilities disabled |
| H6102 | 20-byte `0x33` power, brightness, and `0x15/0x01` RGB layouts | Experimental for #115; value/mask domains, firmware applicability, and physical behaviour unresolved |

Official scene catalogue availability is separate from protocol evidence.  Use
the exact-SKU catalogue fetcher, but do not infer transport, activation, or
readback compatibility from catalogue contents.
