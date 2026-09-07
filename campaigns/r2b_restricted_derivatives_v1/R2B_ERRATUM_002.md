# R2B Erratum 002 — Premium availability timestamp lookahead

Date: 2026-08-27 KST

The root previously labelled `r2b_restricted_derivatives_v1_repaired` is
`INVALID/SUPERSEDED`. Its alignment used source kline open timestamps and did
not enforce that the source close was available before the next executable open.
The immutable root is preserved unchanged with deterministic tree SHA256:
`03141f3b43aa4d7b68e5a04364fe951ff9a22dc7875299cf57388a1564db5fa4`.

The causal repair retains source open/close/availability metadata, uses the
maximum constituent close for 1h/4h aggregates, and rejects exact-boundary or
late observations. No outcome result or final-holdout data was read.

Historical R2B performance conclusions do not exist: the prior registry was
blocked and no valid outcome checkpoint was produced.
