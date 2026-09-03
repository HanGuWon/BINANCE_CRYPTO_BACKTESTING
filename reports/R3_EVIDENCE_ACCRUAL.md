# R3 outcome-blind evidence accrual snapshot

**Snapshot date:** 2026-09-03 KST
**Branch:** `research/r2b-restricted-derivatives-v1`
**State:** `R3_EVALUATION_PREREGISTRATION_BLOCKED`

This is a metadata-only operations report. It contains no response observations,
labels, rankings, significance values, or performance measures. It does not
authorize an evaluation and it does not stop the live collector.

## Frozen identity

- Scientific root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\r3_prospective_context_v1\scientific_raw_v8`
- Implementation commit: `ecebc49dff41eeec33af62c2c85a75c5a0bd2922`
- Scientific source-tree SHA256: `b138931f0d98f4e88aed470c01fce2896e961dc5e0b038dfe196063b73ebc688`
- Registry SHA256: `c623cb36f92ce86b66941a4d525ef8167b2e7fb44ec001523545c0d860feae9a`
- Launch manifest SHA256: `cce8d0341c0a8374b419ebcb0f89d55f30b2f85e746ae730b4b5e9dea7683659`
- Launch seal SHA256: `ab83232d90e800bf8178c6f3d22138382fb102b9d14213e12a798c0f2c68ad85`
- Roster SHA256: `bb05514dfc78cfca3b736488b1454f4cb022da0110e2cbf69f53c505f543ea79`

## Accrual and dependence metadata

The canonical final inventory is
`campaigns/r3_prospective_context_v1/operations/R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903_FINAL.json`.
At this snapshot it reports 94 complete cycles, zero duplicate cycle IDs,
zero missing cycles, two observed UTC calendar days, and five raw UTC six-hour
blocks. The health stream reports 18 gap/restart notices; the checker removes
one affected block and one observation count per notice for conservative
usable-count accounting, leaving four effective blocks. No values are imputed,
and the strict 15-minute availability boundary has 19,734 records checked,
19,734 accepted, and zero rejected.

The input-presence counts after that metadata-only attrition are:

| Hypothesis | Effective observations/events |
|---|---:|
| H01 execution-quality context | 4,682 |
| H02 price × OI quadrant | 3,086 |
| H03 liquidation continuation | 24,117 |
| H04 liquidation reversion | 24,117 |
| H05 crowding × stress modifier | 3,182 |
| H06 BTC/breadth concordance | 3,506 |

The predeclared dependence unit is a complete UTC six-hour block. UTC-day and
day-by-market-state summaries are sensitivity views; event clustering and
simultaneous cross-symbol buckets are retained as metadata only. The checker
received no observed multi-month roster metadata in this snapshot, so the
two-roster-month gate is unmet even though roster files exist in the repository.

## Readiness result

The immutable receipt is
`campaigns/r3_prospective_context_v1/operations/R3_EVALUATION_READINESS_RECEIPT_20260903_FINAL.json`.
It records:

- horizon: zero frozen keys (`HORIZON_NOT_FROZEN`);
- calendar minimum: 2 of 30 days;
- effective independent blocks: 4 of 120;
- roster-month minimum: 0 observed of 2;
- H01, H02, H05, and H06 minima unmet; H03 and H04 event floors met;
- completeness checks pass (no duplicates, missing cycles, boundary violations,
  or imputation), but global minima are not met;
- explicit human authorization is absent;
- `auto_start=false`, final holdout `UNTOUCHED`, and R2B2 `NOT_STARTED`.

The resulting state is intentionally
`R3_EVALUATION_PREREGISTRATION_BLOCKED`. The prior first-pass receipt was moved
to `R3_EVALUATION_READINESS_RECEIPT_20260903_PRECHECK_SUPERSEDED.json`, and the
earlier 92-cycle inventory remains at
`R3_OUTCOME_BLIND_EVIDENCE_INVENTORY_20260903.json`; both are preserved for
provenance. A later horizon amendment must supersede this
contract by hash; no collector, scheduler, or checker invocation may launch an
evaluation automatically.
