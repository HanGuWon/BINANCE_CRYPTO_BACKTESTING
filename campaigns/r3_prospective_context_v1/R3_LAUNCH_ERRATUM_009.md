# R3 Launch Erratum 009 — First v5 Timing Retry

Date: 2026-08-30 KST

The first real v5 persistent run used four absolute target boundaries but was
started with `wait_for_boundary=False` too close to the first scheduled close.
Cycle metadata therefore shows one cycle whose actual start precedes its
scheduled collection time. That root is retained as
`INVALID/SUPERSEDED` and is not used as launch evidence.

A retry is run from a sufficiently old absolute boundary so every scheduled
collection time precedes the actual start while preserving the same persistent
collector/WS architecture. No September roster, outcome, PnL, holdout, or R2B2
data is involved.
