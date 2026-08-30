# R3 Launch Erratum 003 — v4 shadow supersession

Date: 2026-08-30 KST

The first `engineering_shadow_august_v4` root was collected before the final
clock-correction, closed-kline normalization, fresh-root, and per-symbol
completeness gates were implemented. It is retained on D as an operational
artifact and is **INVALID/SUPERSEDED** for launch evidence; it is not modified
or silently resumed.

The canonical fresh shadow root is
`engineering_shadow_august_v4_final`, collected only after those gates were
committed. Its manifest, root tree hash, and receipts are recorded in
`R3_ENGINEERING_SHADOW_AUGUST_V4_RECEIPT.json`.

Neither root contains strategy returns, PnL, rankings, or final-holdout data.
