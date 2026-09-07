# R3 evaluation amendment v2 — single native 15-minute outcome-blind contract

**Status:** `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`  
**Recorded:** 2026-09-04 KST  
**Campaign:** `r3_prospective_context_v1`  
**Primary family:** exactly six rows (`R3_H01`–`R3_H06`) from
`trial_registry.csv`  
**Horizon artifact:** `R3_EVALUATION_HORIZON_V1.json`

This is a new immutable amendment. It does not read or compute response values,
labels, returns, rankings, p-values, or candidate performance. The v8 collector
remains append-only under its sealed identity. The only human authorization in
this amendment authorizes the horizon design; it does **not** authorize an
evaluation run.

## 1. Horizon and causal timing

The sole preregistered horizon is
`R3_HORIZON_15M_NEXT_NATIVE_BAR_V1` (`interval=15m`, `bars=1`, `primary=true`,
`alternative_horizons=[]`). Its selection basis is
`EX_ANTE_NATIVE_COLLECTION_CADENCE_AND_MECHANISM_ALIGNMENT`. No alternate
horizon, threshold, subgroup, or post-hoc search is permitted.

For a decision at `t`, `T_exec` is the next executable native 15-minute open.
The symbolic response interval is exactly `[T_exec, T_exec + 15m]`; this notation
does not authorize opening any response or price field during collection. A
future evaluation may use the already frozen closed-kline log-price estimand

\[
Y_{i,t} = \log(C_{i,T_{exec}+15m}/C_{i,T_{exec}}),
\]

only after a separately authorized evaluation phase. Every feature source must
satisfy the strict point-in-time rule

`source_available_time < next_executable_open_time`.

For native 15-minute premium klines, `source_available_time` is the native
kline close. For any derived 1-hour or 4-hour bucket, it is the maximum close
of all complete constituent native bars. Equality at the executable open is
rejected. A source-open timestamp, mark-price substitution, or future response
receipt cannot satisfy the rule.

The preceding V1 amendment remains byte-for-byte unchanged. Its SHA256 is
`27276b4d3b66d25c987fadbac531df3cfd741dbd43625406fdc342e89c2f1c39` and its
disposition is `SUPERSEDED_PREREGISTRATION_BLOCKED`: V1 lacked a frozen horizon
and its lifetime `missing_cycle_count == 0` condition conflicted with legitimate
recorded gaps. This is a preregistration-contract supersession, **not** invalid
outcome evidence; no V1 outcome evidence exists.

## 2. Observation, gaps, and inference

Each hypothesis uses only an eligible decision boundary and complete required
metadata. Missing components, incomplete buckets, source-unavailable windows,
restart gaps, rollover gaps, and explicit missing cycles are not imputed,
forward-filled, zero-filled, backfilled, or repaired with future data. Raw
counts remain descriptive. An affected observation/event is censored from the
primary estimand by the eligibility rule, while its gap metadata is preserved.
A response unavailable at the end of an eligible segment is right-censored and
excluded. A force-order stream with no event is
`NO_FORCEORDER_EVENT_OBSERVED`, not a zero event. Holdout rows never complete a
response or a minimum.

Every gap record has a UTC start, an optional UTC end, a category, and a stream.
Categories are limited to the recorded metadata classes: `MISSING_CYCLE`,
`RESTART_GAP`, `SOURCE_UNAVAILABLE`, `ROLLOVER_GAP`, and `INCOMPLETE_BUCKET`.
The interval is mapped to every UTC six-hour block it intersects. A point gap
belongs to its containing block; an interval that reaches a six-hour boundary
includes both adjacent blocks. Multiple gaps in one block exclude that block
once, with a stable sorted reason set. A gap spanning blocks excludes each
affected block. Legitimate gaps are preserved and never silently removed;
integrity failures (duplicate IDs, malformed or unaccounted intervals, invalid
hash/replay, or a strict-boundary violation) are global blockers.

The primary independent unit is a complete UTC six-hour block
(`utc_6h_block_id`), with symbol retained as a secondary clustering key. The
primary interval procedure is a wild cluster bootstrap over complete eligible
UTC six-hour blocks with 10,000 independent Rademacher draws and a fixed seed
of `1729`. A secondary sensitivity uses a symbol-and-block cluster-robust
sandwich estimator. No block crosses a gap. For the single native horizon, the
predeclared Newey–West sensitivity lag is `ceil(15m/15m)-1 = 0`.

The family-wise error rate is controlled across exactly six primary tests with
Holm step-down at two-sided `alpha = 0.05`. H03/H04 retain their predeclared
directional alternatives, but the two-sided bootstrap statistic remains the
family gate. No threshold, horizon, feature, polarity, or subgroup variants may
be added after this amendment.

## 3. Frozen estimands

The six estimands below are copied from V1 without a post-outcome redesign and
are now evaluated only at the one frozen horizon above.

### R3_H01 — execution-quality context

\[
s_{i,t}=10^4(ask-bid)/mid,\qquad
m_{i,t}=(ask\,bidQty+bid\,askQty)/(bidQty+askQty),\qquad
d_{i,t}=(m_{i,t}-mid)/mid.
\]

`theta_H01 = (Cov(Y,s), Cov(Y,d))`, estimated by the predeclared
block-clustered projection of `Y` on `(s,d)` and an intercept. H01 is context
only and never a standalone entry rule.

### R3_H02 — price × open-interest quadrant

\[
q_{i,t}=(sign(C_{i,t}-C_{i,t-1}),\ sign(OI_{i,t}-OI_{i,t-1}))
\in\{(+,+),(+,-),(-,+),(-,-)\}.
\]

Zero or missing components are ineligible. `theta_H02` is the fixed four-cell
conditional-mean vector and omnibus four-cell equality statistic; no reference
cell is chosen after inspection.

### R3_H03 — liquidation continuation

For each observed force-order event `e`, retain the frozen pressure
`p_e = sign_e * last_filled_quantity_e * average_fill_price_e`, where
`sign_e=+1` for forced `SELL` and `-1` for forced `BUY`, and let `u_e=-sign_e`.

\[
theta_{H03}=E[u_e\,Y_{i(e),t(e)}\mid e\ observed].
\]

The directional alternative is `theta_H03 > 0`; stream and restart gaps are not
events and cannot be imputed.

### R3_H04 — liquidation reversion

Using the identical event set and `u_e`,

\[
theta_{H04}=E[-u_e\,Y_{i(e),t(e)}\mid e\ observed].
\]

The directional alternative is `theta_H04 > 0` (equivalently `E[u_e Y] < 0`),
and is a distinct preregistered hypothesis.

### R3_H05 — crowding × stress modifier

Let `f_{i,t}=lastFundingRate` from `/fapi/v1/premiumIndex` and
`p_{i,t}=close` of the latest completed
`/fapi/v1/premiumIndexKlines?interval=15m`. Let
`b_{i,t}=sign(C_{i,t}-C_{i,t-1})`. Both components must be available before
the next executable open.

\[
theta_{H05}=\big(Cov(bY,f),\ Cov(bY,p)\big).
\]

H05 is modifier-only; neither component creates a standalone entry and mark
price is never substituted for premium.

### R3_H06 — BTC/breadth concordance

For the frozen selected universe `U_t`,

\[
C_t=|U_t|^{-1}\sum_{j\in U_t}sign(r_{j,t})sign(r_{BTC,t}),\qquad
r_{j,t}=\log(C_{j,t}/C_{j,t-1}).
\]

Symbols without a valid return are removed from the denominator. The estimand is
`theta_H06=Cov(Y,C_t)` from the block-clustered projection; BTC is context only
when it is not in the selected Top50.

## 4. Evidence minima and state rule

These are fixed operational sufficiency gates, not optimization targets:

| Gate | Requirement |
|---|---|
| Calendar span | at least 30 complete UTC calendar days after first eligible cycle |
| Dependence units | at least 120 complete eligible UTC six-hour blocks |
| Roster diversity | at least two distinct verified roster months |
| H01 | at least 5,000 eligible book-ticker observations |
| H02 | at least 5,000 eligible symbol-quadrant observations |
| H03 | at least 1,000 observed force-order events with eligible responses |
| H04 | the same 1,000-event floor, counted independently |
| H05 | at least 5,000 complete funding+premium pairs |
| H06 | at least 5,000 eligible symbol/breadth observations |

The checker reports raw and primary-eligible counts separately. It no longer
requires lifetime `missing_cycle_count == 0`; all explicit gaps must instead be
accounted for by the block map. A frozen contract with unmet calendar, block,
roster, or hypothesis minima is
`R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`. An invalid contract or
integrity failure is `R3_EVALUATION_PREREGISTRATION_BLOCKED`. If all minima pass,
the state is `R3_EVALUATION_ELIGIBLE_NOT_STARTED` until a separate human
evaluation authorization is recorded. The horizon authorization in this file
never sets `evaluation_human_authorized=true` and never starts a run.

## 5. Immutable firewall

This amendment forbids access to final-holdout rows, R2B2 materialization,
forward-label stores, response/return/PnL/Sharpe/hit-rate fields, historical
ranking, and performance reports. The metadata-only checker may read only v8
identity, health, manifest-chain, roster metadata, explicit gap metadata, and
the outcome-blind inventory. Any forbidden token in a path or key fails before
eligibility is reported. The amendment, horizon, manifest, receipts, and reports
are append-only; a future design supersedes them by hash and never edits them in
place.
