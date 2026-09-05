# Work phase wp2 — SOL core correctness repairs

All changes in this phase are generic-harness repairs in the isolated branch.
No dedicated R3 scientific executor, frozen result, historical conclusion,
checkpoint, return, or holdout file may be read or rewritten.  The six repair
units below are implementation contracts, not prose intentions; the cited
tests are the required regression evidence.

## A02 — readiness and evidence-inventory contract

`ops/r3/check_r3_evaluation_readiness.py` must validate a strict, typed
metadata envelope.  A missing required value is an error; it must never be
converted to zero by `_number(..., default=0)` or by a fallback between raw and
usable counts.

Required top-level mappings and fields are:

* `availability_and_gaps`: mapping containing boolean
  `gap_accounting_complete`, non-negative integer counters
  `health_gap_count`, `health_restart_count`, `source_unavailable_records`,
  `rollover_gap_count`, and `incomplete_bucket_count`, plus a `gap_records`
  list.  Every `gap_records` item is a mapping with category in the exact set
  `{MISSING_CYCLE, RESTART_GAP, SOURCE_UNAVAILABLE, ROLLOVER_GAP,
  INCOMPLETE_BUCKET}`, ISO-UTC `start_time` (or the legacy `start` accepted
  only when it is normalized to the same field), optional ISO-UTC `end_time`,
  and a deterministically derived UTC six-hour block set.  Under the strict
  `gap_blocks_by_scope` schema, each item must expose a list of unique valid
  block IDs and valid scopes; list order is canonicalized before comparison.
* `cycles`: mapping containing non-negative integer `cycle_count`,
  `missing_cycle_count`, and `duplicate_cycle_ids`; a `cycle_id_timestamps`
  list whose every item is exactly an object with string `cycle_id` and
  ISO-UTC `timestamp`; and a `metadata_stream` object.  The metadata-stream
  object must contain non-negative integer `complete_records`, `files`,
  `records`, `source_available_records`, `source_unavailable_records`, and
  `gap_records`, non-negative integer `symbols`, a mapping
  `continuity_state_counts`, and ISO-UTC `first_timestamp`/`last_timestamp`.
  `cycle_count` equals the length of `cycle_id_timestamps`, IDs are unique,
  and `missing_cycle_count`/`duplicate_cycle_ids` reconcile to the observed
  cycle sequence.  Stream-level records in the top-level `streams` mapping
  must expose the same typed counters (`complete_records`, `records`,
  `source_available_records`, `source_unavailable_records`, `gap_records`,
  `symbols`, `first_timestamp`, `last_timestamp`); the checker compares these
  to `cycles.metadata_stream` and rejects omission, type mismatch, or
  disagreement rather than selecting a convenient fallback.
* `calendar`: mapping containing non-negative integer
  `independent_utc_days` and `independent_utc_6h_blocks`, exact maps
  `usable_blocks_by_hypothesis` and `usable_days_by_hypothesis` with keys
  exactly `H01`–`H06` and list values of unique canonical block/day IDs, and a
  `roster_contribution_by_hypothesis` map with keys exactly `H01`–`H06`.  Each
  roster-contribution value is an object with `complete_count` (positive
  integer), `block_ids` (unique list), `day_ids` (unique list), and
  `roster_sha256` (64 lowercase hex characters); `complete_count` equals the
  number of complete rows represented by those IDs, the IDs are subsets of the
  corresponding usable maps, and every SHA occurs in
  `used_roster_identities`.  No scalar/object fallback is permitted.
* `causal_input_presence`: mapping with exactly `H01`–`H06`; each hypothesis
  entry has non-negative integer `raw_observations` and
  `usable_observations` (and the corresponding symbol-bucket/event field
  required by its H contract), with `0 <= usable <= raw`.  The field names are
  H01 `usable_observations/raw_observations`, H02/H05/H06
  `usable_symbol_buckets/raw_symbol_buckets`, and H03/H04
  `usable_events/raw_events`.  No alternate field is silently substituted.
* `observed_at_utc`: required RFC-3339 timestamp with an explicit UTC offset.
  `evaluate_readiness(..., reference_time=...)` supplies the reference clock
  (UTC; production defaults to the call-time clock, synthetic tests pass a
  fixed value).  The checker rejects an observation older than 7 calendar days
  (`reference_time - observed_at_utc > timedelta(days=7)`) or more than five
  minutes in the future (`observed_at_utc - reference_time > timedelta(minutes=5)`),
  and rejects naive/non-finite timestamps.  This is the complete freshness
  window; no filesystem mtime or local timezone is consulted.
* `primary_family_metadata`: the existing exact six-key H01–H06 metadata,
  frozen implementation/source/registry/root/launch-manifest hashes, `SEALED`
  seal, and strict availability rule
  `source_available_time < next_executable_open_time`.  A source-open time is
  not an availability time.  Hashes and identity fields must agree with the
  referenced manifest and causal root.

Reject closed-form failures for missing fields, wrong JSON types, negative or
non-integral counters, stale timestamps, mismatched hashes/identities, a false
`gap_accounting_complete` when any aggregate counter is positive, aggregate
counts that do not reconcile to explicit records, duplicate or out-of-scope
block IDs, missing per-hypothesis maps, and any source observation at or after
the next executable open.  The checker must preserve the existing exact
boundary rejection and must not repair metadata by subtraction or defaulting.

Required regression paths are `ops/r3/tests/test_evaluation_readiness.py`,
`ops/r3/tests/test_r3_checker_contract_v2.py`, the existing
`ops/r3/tests/test_inventory_accounting_v2.py`, and a new focused
`ops/r3/tests/test_wp2_readiness_contract.py` covering absent/stale/type/
identity/counter mismatches and explicit gap receipts.  The test fixtures are
synthetic metadata only and do not read checkpoint or return artifacts.

## A04 — timestamp/position and embargo contract

Keep the authoritative signatures:

```python
global_calendar_split(
    frame, *, timestamp_column, train_end, validation_end, timeframe,
    operational_embargo_bars=0
) -> GlobalCalendarPartitions
chronological_split(frame, train_fraction=0.6, validation_fraction=0.2,
                    embargo_bars=0)
expanding_walk_forward(n_observations, minimum_train, validation_size,
                       test_size, step_size=None, embargo_bars=0)
```

`global_calendar_split` treats `train_end` and `validation_end` as UTC
timestamp labels, obtains the exact step from `{15m:15min, 1h:1h, 4h:4h}`,
and applies the frozen purge map `{15m:96, 1h:24, 4h:6}`.  The exact half-open
intervals are:

* train: `timestamp < train_end - purge_bars[timeframe] * step`;
* validation: `train_end + operational_embargo_bars * step <= timestamp <
  validation_end - purge_bars[timeframe] * step`;
* test: `timestamp >= validation_end + operational_embargo_bars * step`.

Define the exact helper
`next_executable_open(source_available_time: pd.Timestamp, timeframe: str) ->
pd.Timestamp`: normalize the input to UTC, require it to be finite, and return
the first canonical timeframe-grid open strictly greater than that availability
timestamp (`15m=15min`, `1h=1h`, `4h=4h`).  The caller stores `decision_time`
separately and must assert
`source_available_time < entry_time == next_executable_open(source_available_time,
timeframe)`; an equal source/open boundary is rejected, never rounded into a
valid observation.  This helper's return value, not a row label or `entry_bar`,
is the only admissible next-open lookup.  Outputs from every splitter preserve
the original frame index and row order.  `chronological_split` and
`expanding_walk_forward` operate on stable integer row positions via `.iloc`;
they may return positions, but never treat arbitrary index labels as positions.
The CLI `_outer_positions` and `_selected_walk_forward` must delegate to these
helpers rather than duplicate boundary arithmetic, and must pass both the
decision timestamp and source-availability timestamp into the provenance
record so equality/future-observation tests exercise the same function.

Required tests: exact boundary/equality rejection and timeframe-step cases in
`tests/test_r16_semantics.py` and `tests/test_splits_statistics.py`, plus a
focused non-default-index CLI test proving labels are retained and a future
observation cannot enter validation through an index/position collision.

## A05 — fixed-entry and timeline accounting contract

For direction `d in {+1, -1}`, entry open `O_e`, exit open `O_x`, crossed bars
`j in [e, x)`, and funding rates `r_j`:

```text
gross_return       = d * (O_x / O_e - 1)
funding_cashflow   = -d * sum(r_j)
funding_cost       = -funding_cashflow       # compatibility alias only
net_return         = gross_return + funding_cashflow
                     - fee_cost - spread_cost - slippage_cost
```

Positive funding therefore decreases a long and increases a short; negative
funding has the opposite effect.  Entry and exit fee, half-spread, and
slippage costs are charged exactly once at their defined open prices.  The
  per-bar equity timeline must use this normative additive-within-bar,
  multiplicative-across-bars factor (funding is a return cashflow, not a
  second compounding factor):

  ```text
  bar_factor_j       = 1 + d * (O_(j+1) / O_j - 1) - d * r_j
  timeline_factor    = product(bar_factor_j for j=e..x-1)
  timeline_net       = timeline_factor - 1 - fee_cost - spread_cost - slippage_cost
  ```

  `fee_cost`, `spread_cost`, and `slippage_cost` are each deducted once at
  their entry/exit boundary in the timeline cashflow ledger (the displayed
  closed form is the resulting return-unit value).  The implementation must
  expose the product before costs for audit and compare it to an independent
  product reproduction within `1e-12`; no additive short-return shortcut may
  remain.  Preserve existing public `gross_return`, `funding_cost`, and cost
  fields while adding the explicit `funding_cashflow` field.

The fixed-entry trade fields are authoritative for reported `gross_return`,
`funding_cashflow`, costs, and `net_return`.  The timeline is a path-dependent
diagnostic and must equal exactly the normative product above (within `1e-12`)
without overwriting or redefining those fields.  With one crossed bar and the
same costs, its terminal return equals the fixed-entry `net_return` within
`1e-12`; with multiple bars, any path difference is expected, labelled, and
tested rather than hidden.  Required tests in
`tests/test_backtest.py` and `tests/test_corrections_v2.py` cover zero,
positive, and negative funding for both directions, intermediate prices, cost
timing, the product/tolerance invariant, and the explicit fixed-entry versus
timeline reconciliation rule.

## A06 — Deflated Sharpe frequency/unit contract

Make one explicit unit boundary between `src/binance_research/statistics.py`
and `src/binance_research/cli.py`.  The following API is normative; no
alternative positional/annualized signature is admissible:

```python
def deflated_sharpe_probability(
    observed_sharpe_periodic: float,
    trial_sharpes_periodic: Sequence[float],
    observations: int,
    *,
    skewness: float,
    excess_kurtosis: float,
    moment_policy: Literal["observed", "gaussian_zero"] = "observed",
) -> float
```

All Sharpe inputs are periodic (bar or explicitly selected validation-period
units); annualization, if reported, occurs exactly once at the presentation
boundary and is never silently mixed into the deflated-Sharpe calculation.
`deflated_sharpe_probability` has no frequency conversion parameter and never
annualizes.  A separate presentation-only helper may compute
`annualized_sharpe = periodic_sharpe * sqrt(periods_per_year)` after requiring
finite positive `periods_per_year`; this helper is not called by DSR.  Moments
must be finite and come from the same periodic return vector when
`moment_policy="observed"`; an explicitly named
`moment_policy="gaussian_zero"` is the only way zero moments may be used.
Reject NaN/non-finite Sharpe or moment inputs, `observations < 3`, fewer than
two trials, and zero trial dispersion with the documented NaN/blocked result.
The CLI must call exactly this API with the periodic return vector's observed
Sharpe, the periodic trial-Sharpe vector, its actual finite observation count,
finite skewness/excess kurtosis, and an explicit `moment_policy`; it must not
pass an annualized Sharpe or use `len(validation)` as a substitute for the
return count.  Independent reference tests must catch annualized-vs-periodic
scale mismatch and omitted/default moments.

## A07 — decision-time regime attribution contract

`_regime_table` must require a `decision_time` (or a `decision_bar` that is
resolved to its source timestamp before entry) on every trade.  It must map to
the latest regime row with `regime_time <= decision_time`; `entry_bar` is never
an input fallback and a missing decision field is a hard error.  The CLI must
pass the validation decision-time series to the helper.  Add a regression
fixture where the regime changes after decision but before entry; attribution
must remain the pre-change regime.

## A12 — arbitrary-index, gap-safe cohort algorithm

`build_cohort_aware_breadth` must create a stable positional column
`row_pos = np.arange(len(frame))`, group with `sort=False`, and use `.iloc` on
integer position arrays for every group/segment operation.  Within each
symbol/timeframe stream, timestamps are strictly increasing and unique; the
expected step is explicit (`15m`, `1h`, or `4h`), and a missing/off-grid bar
starts a new segment.  Segment statistics are assigned back by `row_pos`,
then the original index (including duplicate labels such as `[10, 20, 10,
30]`) and original column order are restored.  Duplicate timestamps remain a
hard error; duplicate index labels are allowed because labels are never used
as row selectors.  Add tests for non-default/duplicate labels, missing bars,
gap reset, appended-future invariance, and index restoration.

## Review closure and handoff evidence

The independent reviewer must re-audit this plan and return `VERDICT: PASS`
before A→B.  During C, run the focused readiness/split/accounting/statistics/
CLI/features tests, the existing R3 metadata verifiers, and the source-bound
pytest receipt.  Mark each wp2 task complete only with an exit-code-zero receipt;
the phase D handoff must include `checkOutput` and `exitCode: 0`, followed by
clean scientific-source status and the wp2 commit SHA.  Only after D is synced
may the loop enter the next planning phase.
