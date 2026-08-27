# R2A.2 Aggregation Erratum 001

Date: 2026-08-27 (KST)

The corrected v10 outcome checkpoints were sealed before this aggregation
audit. Before any aggregate performance was inspected, the prior aggregator
was found to use fold-resampling with 2,000 draws and to omit the frozen
top-symbol and catastrophic-reversal grading gates. The frozen campaign
contract requires calendar-block resampling that preserves all symbols
together, 1,000 draws, seed 1729, and all replication criteria.

The repaired aggregator implements calendar-month blocks on the equal-weight
decision-time portfolio series, samples=1000, seed=1729, full-registry
Benjamini–Hochberg q-values, minimum four valid folds, positive direction in
at least 75% of valid folds, aggregate HAC |t| at least 3, maximum top-symbol
share at most 0.5, and the catastrophic-reversal fail rule. Missing evidence
fails closed as `INSUFFICIENT_EVIDENCE` or `INSUFFICIENT_FOLDS`.

No hypothesis, feature, side, horizon, threshold, registry entry, outcome
checkpoint, or holdout boundary was changed. The outcome implementation is
separately pinned as SHA
`99a37ae161d3791fb9a5d040f7cb9772492a5ed4`; the post-outcome aggregation
implementation SHA is recorded in `aggregate_manifest.json` when the sealed
v10 root is aggregated. The previous v10 outcome files remain immutable.
