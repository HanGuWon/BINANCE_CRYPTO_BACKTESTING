# R2A.2 Verification — sealed v10

Date: 2026-08-27 (KST)

## Provenance and accounting

- Canonical checkpoint root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2a2\checkpoints_v10`
- Outcome implementation SHA: `99a37ae161d3791fb9a5d040f7cb9772492a5ed4`
- Outcome registry SHA256: `d80fa57832714d7073d1a769c1422eb384b798ed1a929632a58d1948e3b83f3d`
- Outcome source-tree SHA256: `07572aaae5b70f05958fe36c223b2569439547b2cf99efabc3001038cb4f2777`
- Outcome `source_dirty`: `false`
- Checkpoint manifest SHA256: `09272983998c0f039e3af30cc4f05a1858cdd4d7c0f4aec0d5c7311e5a54b76c`
- Accounting: `6048 / 6048` units (756 trials × 8 folds), failed units `0`.
- Checkpoint verifier: PASS; 6048 files, 84,815,811 trade rows; sign, holdout, overlap, and next-open violations all `0`.

## Qualification and tests

The explicit-sign slow-reference qualification covered the committed 756-trial
registry: Spot LONG and UM LONG/SHORT across 15m, 1h, and 4h, every registered
horizon, synthetic positive/negative funding events, funding/funding_zscore,
and a gap segment. The targeted qualification/directional/segment gate passed
(`11 passed` in the qualification gate). Aggregation contract tests passed
(`19 passed`). Full pytest after the aggregation commits passed (`147 passed,
1 warning`). The receipt is in
`.codexclaw/evidence/01a0230d-0a21-7e02-ab97-a10534161680/test-receipt.json`.

## Aggregation provenance and result

- Aggregation implementation SHA: `bdbe381ae849dfdb55c6a0d55b4c3a7bc30ebe52`
- Aggregation script SHA256: `1177700f98907f41d646c7eac33609a90926b682496976e6fa2653ec7ac0eb0d`
- Aggregation source dirty: `false` at execution.
- Bootstrap: calendar-month blocks (explicit calendar-block realization), all symbols together, `1000` samples, seed `1729`.
- Valid-fold range: `6–8`; BH-FDR survivors: `520`; maximum aggregate-valid top-symbol share: `0.1132382068`.
- Catastrophic-reversal failures: `541` trials.
- Temporal replication: `0` of `756`; all statuses `NO_REPLICATION`.
- Candidate shortlist: empty (no trial met every frozen criterion).
- Cohort diagnostics are distinct: Top20/Top50/Top100 universe symbol counts `198/407/551`; MFE/MAE is diagnostic-only with an explicit unavailable-path reason.
- Final holdout: `UNTOUCHED`; holdout proof checks decision, entry, and exit timestamps strictly below each timeframe boundary.

The aggregate artifact hashes are recorded in
`aggregate_manifest.json`; the prior invalid/superseded checkpoint roots and
their SHA256SUMS remain preserved on D:. No outcome checkpoint was rewritten.

Historical R2A/R2A.1 disposition remains the explicit directionally-invalid
one documented in `R2A2_ERRATUM_002.md`: their mixed-sign execution cannot
support per-direction claims, and no historical conclusion was silently
rewritten.

## Verdict

**VERIFIED — R2A.2 NO ROBUST TEMPORAL/HORIZON EVIDENCE**

This is a complete, preregistered pre-holdout null result under the frozen
replication gates, not evidence for a positive strategy. R2B was not started
and the final holdout was not accessed.
