# R1.5 verification report

## Implementation provenance

- Branch: `research/r1-full-history-v1`
- Protocol parent: `4d7377214ad0fd272911f6247eb612b10ed882b4`
- Immutable R1A parent: `5afa3008a49a5c2cac1678c957dbcb35068144be`
- Implementation commit: `357b3566748862fd4548351f3a2ea0bae376abea`
- Campaign code hash: `2957d59e9a1f3ac6f129a274cd6f925e7fdc95e207daaafe7cd77f4a65d7b427`

## Gates A–E

Gate A passed. ListObjectsV2 pagination was implemented with deterministic
ordering, duplicate protection, continuation-token loop protection, malformed
XML failure, and missing-token failure. The successful kline census consumed
4,686 pages: 3,699 Spot pages and 987 UM pages. A transient connection-reset
run was not accepted as data and the successful rerun used bounded network
retries.

Gate B passed for the four anchors at the archive level. Spot BTCUSDT and
ETHUSDT run from 2017-08 through 2026-07 (108 monthly objects each); UM BTCUSDT
and ETHUSDT run from 2020-01 through 2026-07 (79 monthly objects each). The
latest fully archived 15m bar is 2026-07-31 23:45 UTC; the frozen acquisition
cutoff is 2026-08-21 05:00 UTC. Spot has 25 issue-bearing months per anchor,
all explicitly retained as gaps; UM has zero issue-bearing kline months.

Gate C passed for the tested derivative anchors. FundingRate has 79 verified
monthly objects per UM anchor, 7,212 event rows each, with event timestamps and
funding-rate fields intact. PremiumIndexKlines 15m has 79 verified monthly
objects per anchor and 230,008 rows each; seven months per anchor contain
explicit missing-interval warnings. Spot funding/premium remains
`NOT_APPLICABLE`. UM bookTicker exists for a bounded 2023-05–2024-04 window,
but its exact frozen top-book semantics were not promoted without a schema
verification; metrics/bookDepth/liquidationSnapshot roots were not accepted as
substitutes.

Gate D passed as a metadata census, not as a downloaded candidate panel. The
archive contains 3,682 Spot historical symbols and 986 UM symbols. The frozen
return-independent policy leaves 670 Spot candidates and 832 UM perpetual-style
candidates; 3,012 Spot and 154 UM exclusions are recorded with reasons.
Broad-universe monthly Top-20/50/100 cohort counts are therefore
`NOT_CONSTRUCTED`: no candidate membership was selected, and no monthly cohort
file is claimed. Constructing those cohorts requires the prior-month
quote-volume acquisition that remains blocked below.

Gate E produced an actual size estimate and stopped before broad acquisition.
Eligible candidates require 46,801 15m monthly objects and 5,273,148,503
compressed bytes. A Top-50 selected-panel upper bound is approximately 9,350
objects and 1.2–1.3 GiB compressed, but exact membership cannot be computed
without reading prior-month quote volumes for the eligible candidate set.
Current free disk was 30,222,815,232 bytes at measurement. Candidate raw plus
derived Parquet and temporary space does not leave a defensible safety margin,
so no broad universe download was launched.

## Tests and commands

Executed from the clean implementation commit:

```text
python -m compileall -q src tests scripts
python -m pytest --collect-only -q   # 55 collected
python -m pytest -q                   # 55 passed
python scripts/r15_archive_census.py --workers 2
python scripts/build_r15_full_history.py --workers 2
python scripts/build_r15_derivative_history.py
python scripts/materialize_r15_anchor_panel.py
```

Raw archives and processed Parquet are ignored by Git. Only small campaign
metadata, manifests, census summaries, code, and tests are tracked.

## Holdout and scientific scope

No indicator performance, return correlation, Sharpe, parameter ranking, or
candidate selection was performed. `final_holdout_status=UNTOUCHED`.

## Verdict

PARTIALLY VERIFIED — R1 BLOCKERS REMAIN
