# R2B readiness audit

Audit disposition: **`R2B_BLOCKED_IMPLEMENTATION`**

This is an adversarial pre-outcome audit. It does not reopen R2A.2, produce an
R2B result, read the final holdout, or start R2B.

## Provenance finding

The original R1.5 derivative builder contains `for symbol in
("BTCUSDT", "ETHUSDT")`. The R1.7 panel consequently had only two acquired
premium anchors while the Binance Vision census reported 916 UM premium symbol
prefixes. Its six premium coverage rows were only 0.034537–0.042065 and were
correctly classified `R2B_RESTRICTED`. This is a recoverable acquisition
completeness defect, not a conclusion about market availability.

The repair is isolated from R1: `premium_archive_manifest.csv` records 5,647
pre-holdout 15m objects for 189 selected UM symbols, all local files exist, and
all 5,647 checksums pass. Archive month `2024-02` and later are absent. The
formerly labelled canonical repaired materialization is now
`D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1_repaired`.
It will be preserved, hash-recorded, and marked `INVALID/SUPERSEDED` because
the source-open alignment admitted observations whose close-time was not yet
available at the executable open. A new causal root must be produced by the
repaired source.
It has 8,357,398 rows across 1,467 Parquet partitions, with 193 panel symbols;
four selected symbols have no pre-holdout premium archive. No R1 raw object or
panel was modified.

## Corrected availability-conditioned coverage

| feature | timeframe | eligible rows | finite rows | fraction |
| --- | ---: | ---: | ---: | ---: |
| premium | 15m | 6,367,539 | 6,364,083 | 0.999457 |
| premium | 1h | 1,591,886 | 1,591,022 | 0.999458 |
| premium | 4h | 397,973 | 397,757 | 0.999457 |
| premium_zscore | 15m | 6,367,539 | 6,336,534 | 0.995131 |
| premium_zscore | 1h | 1,591,886 | 1,564,763 | 0.982962 |
| premium_zscore | 4h | 397,973 | 372,559 | 0.936141 |

Residual missingness is labelled explicitly (`ARCHIVE_NOT_ACQUIRED`,
`FEATURE_WARMUP_OR_ZERO_VARIANCE`, `GAP_QUARANTINED`, or
`NO_RESEARCH_ELIGIBLE_ROWS`). It is not converted to a zero signal or silently
dropped.

## Implementation blocker

The frozen source has a value implementation for `premium_zscore90`, but no
`sig_premium`, no `sig_premium_zscore`, and no documented threshold/sign rule;
`derivatives.premium` is not a `CORE_FEATURE_SPECS` entry. Choosing a sign or
threshold would change the scientific question. Therefore the 36-row registry
is intentionally metadata-only (`UNDEFINED_SIGNAL_SEMANTICS`,
`BLOCKED_IMPLEMENTATION`) and no outcome executor or qualification claim is
valid yet.

Promotion requires an explicit reviewed semantics amendment, implementation,
directional tests, all-timeframe/both-side slow-reference qualification, clean
source commit, and a fresh full pytest receipt. Until then the only defensible
state is `R2B_BLOCKED_IMPLEMENTATION`.
