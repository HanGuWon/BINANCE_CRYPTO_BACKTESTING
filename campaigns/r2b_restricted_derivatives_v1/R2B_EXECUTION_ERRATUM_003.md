# R2B execution erratum 003 — v6 membership-gap continuity defect

Date: 2026-08-28 KST

The sealed v6 lineage is preserved unchanged at
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2b_restricted_derivatives_v1_checkpoints_v6`.
It is superseded as scientific evidence by this erratum and must not be called
verified. The defect is an execution-continuity error, not a change to the
72-row hypothesis family or any frozen economic rule.

## Independent recomputation

All 576 unit JSON files and their trade Parquets were read directly. The audit
found 11,826,364 trade rows. Counts are:

| invariant | violations |
|---|---:|
| signal sign | 0 |
| source availability | 0 |
| per-symbol overlap | 0 |
| net-return identity | 0 |
| January 2024 | 0 |
| final-holdout | 0 |
| exact next-open | 438 |
| exact horizon-exit | 4,094 |

The violations affect 474/576 checkpoint units, all 72/72 trials, and 62
symbols (including IOTAUSDT). The v6 run therefore has status:

`INVALID/SUPERSEDED — EXECUTION MEMBERSHIP-GAP CONTINUITY DEFECT`

## Root cause

The causal panel contains only periods in which a symbol was selected into the
Top50 universe. A symbol can therefore have October rows, no November rows,
and December rows while retaining one original `segment_id`. The old runner
grouped only by that identifier and treated adjacent surviving dataframe rows
as adjacent bars. Consequently `local + 1` and `local + horizon + 1` could
cross the missing month, violating both next-open and exact-bar horizon rules.

The corrective implementation derives an execution segment from both the
original segment identifier and exact timestamp continuity for the timeframe;
missing execution-price continuity is fail-closed. v6 is never modified or
resumed.

The old v6 `run_manifest.json` SHA256 is
`a47ad4d8f2399f2b8cd93650ec483158cbe1b4a54f2ef318eb65d9cbdd84c5e5` and the
old aggregate SHA256 is
`e261909d1be97585e1235f181680bef5f64794c360bf1e92c54c1e772ab9c85d`.
