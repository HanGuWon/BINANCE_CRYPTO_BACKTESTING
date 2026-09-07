# R2B corrected pre-holdout replication report

Final verdict: `VERIFIED — R2B CORRECTED PRE-HOLDOUT COMPLETED, NO ROBUST TEMPORAL REPLICATION`

This is a post-outcome correctness replication. No hypothesis, polarity,
threshold, horizon, cost, fold, funding, FDR, bootstrap, or grading rule was
changed. Final holdout and R2B2 were not accessed.

## Identity and v6 disposition

* Branch: `research/r2b-restricted-derivatives-v1`
* Final HEAD at report preparation: `1c44663d753ca7706a5dbeb7c41cc2d90241ebbe`
* Corrected implementation commit: `67d006ae3205384e08a3e8ed68f8225708077305`
* Corrected scientific source-tree SHA256: `0c3c264e6685b8d3704f4cccc1214448af0ae9036a1d8977d29f086553b98d93`
* Registry SHA256 unchanged: `3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302`

The immutable v6 root remains `INVALID/SUPERSEDED — EXECUTION MEMBERSHIP-GAP
CONTINUITY DEFECT`. Direct recomputation found 11,826,364 trade rows, 438
exact next-open violations, 4,094 exact horizon-exit violations, 474/576
affected units, 72/72 affected trials, and 62 affected symbols. Sign,
availability, overlap, net-return, January-2024, and holdout violations were
all zero. See `R2B_EXECUTION_ERRATUM_003.md` and the preserved v6 hashes.

## Corrected execution

Execution segments split on original causal `segment_id`, any timestamp delta
other than the exact timeframe step, and missing/nonfinite execution prices.
Within a segment, entry is exactly one timeframe step after decision and exit is
exactly `horizon_bars` steps after entry. Funding archives fail closed when
unavailable or corrupt; an empty event interval is distinct from missing data.

Corrected checkpoint root:
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2b_restricted_derivatives_v1_checkpoints_v7`

`run_manifest.json` SHA256:
`8ce7f75620c578dab808ddf7d7e7b2d610135680d5ed4515999cd899753f0602`.

The enhanced verifier returned `PASS`: 576/576 terminal `VALID` units,
11,823,724 trade rows, and zero sign, next-open, horizon-exit,
source-availability, overlap, net-return, January-2024, holdout, schema,
trade-hash, and source-identity violations.

Funding audit found 193/193 causal-panel symbol directories present, 0 empty,
and 0 corrupt zip archives. Real qualification observed both positive and
negative funding events.

## Qualification

The optimized executor and slow reference agreed twice with identical normalized
receipt SHA256 `308491b5eca4ca6d34e8c30eeb037268f66cdd5d49a58d0929251d93f254cbef`.
The matrix covers UM BTCUSDT 15m/1h/4h, LONG/SHORT, every registered horizon,
both premium features and both variants, actual positive/negative funding,
synthetic positive/negative/none funding, and membership/original-segment/
missing-price adversarial gaps. 2,752 records were compared; all gap fixtures
produced zero trades crossing a boundary.

## Contract-conforming aggregation

The old v6 `aggregate_1.json` and `aggregate_2.json` remain preserved as
nonconforming/superseded evidence. The corrected aggregator uses equal-weight
decision-time portfolio observations, joint calendar-month blocks (1,000
samples, seed 1729), full-family BH-FDR q=0.05, positive-fold fraction
`mean(fold_aggregate_mean > 0)`, aggregate HAC, aggregate absolute
top-symbol share, and the exact catastrophic-reversal rule.

Canonical artifacts are under `corrected_aggregation_v7/`. Two complete runs
were byte-identical. `aggregate_manifest.json` SHA256 is
`30f217f4635878a1b6a754900ab6027b9666aaef72d0ade3a8afc25d37e1722d`.

| gate | count |
|---|---:|
| BH-FDR survivors | 55/72 |
| positive-fold fraction ≥ 0.75 | 3/72 |
| aggregate HAC \|t\| ≥ 3 | 46/72 |
| aggregate top-symbol share ≤ 0.50 | 72/72 |
| catastrophic-reversal pass | 19/72 |
| catastrophic-reversal fail | 53/72 |
| `TEMPORAL_REPLICATION` | 0/72 |

The candidate shortlist is empty. Therefore the corrected result is
`NO ROBUST TEMPORAL REPLICATION`, not a promoted strategy.

## Verification boundary

Targeted R2B tests pass (including execution-gap, verifier, signal, and
aggregation contract tests). Full `python -m pytest -q` was run after the
correction and returned `182 passed, 1 warning in 125.88s (0:02:05)` with exit
code 0; the canonical receipt records its source identity and warning count.
Final holdout remains
`UNTOUCHED`; R2B2 is `NOT STARTED`.
