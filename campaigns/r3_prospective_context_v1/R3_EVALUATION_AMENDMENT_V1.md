# R3 evaluation amendment v1 — outcome-blind unlock contract

**Status:** `R3_EVALUATION_PREREGISTRATION_BLOCKED`
**Recorded:** 2026-09-03 KST
**Campaign:** `r3_prospective_context_v1`
**Primary family:** exactly six rows (`R3_H01`–`R3_H06`) from
`trial_registry.csv`

This amendment freezes the evaluation contract without opening an evaluation
run. It is an outcome-blind governance artifact: no response values, labels,
returns, rankings, p-values, or candidate performance are read or computed by
this amendment. The live v8 collector remains append-only and continues under
its already sealed identity.

## 1. Eligibility gate and horizon disposition

The only admissible response for a future evaluation is the closed-kline
log-price response

\[
Y_{i,t,h}=\log(C_{i,t+h}/C_{i,t}),
\]

where `i` is a selected UM symbol, `t` is an eligible decision boundary, and
`h` is one **single pre-existing horizon key**. A response is eligible only
when every source used by the feature satisfies
`source_available_time < next_executable_open_time`, and the response endpoint
is strictly before the final-holdout boundary.

The current R3 registry has no `horizon` field, and no separate, immutable
R3 horizon artifact is present. The R2B registry is explicitly not reused.
Therefore `H_frozen = ∅` in this amendment. No horizon may be inferred,
searched, or selected from observations. Until an authorized amendment adds
one exact horizon key and its hash, the readiness state is hard
`R3_EVALUATION_PREREGISTRATION_BLOCKED` and no historical evaluation may run.

## 2. Common observation and inference rules

For each hypothesis, the feature is attached to the first executable open
after its source becomes available. Exact-boundary equality is rejected. A
missing required component, source/response gap, restart gap, rollover, or
incomplete constituent bucket removes that observation from the relevant
estimand; it is never forward-filled, zero-filled, or repaired with future
data. A force-order stream with no event is `NO_FORCEORDER_EVENT_OBSERVED`,
not a zero event. A response unavailable at the end of an eligible segment is
right-censored and excluded. Holdout rows are never used to complete a
response or a minimum.

The primary independent unit is a UTC six-hour block (`utc_6h_block_id`), with
symbol retained as a secondary clustering key. The primary interval procedure
is a wild cluster bootstrap over complete UTC six-hour blocks (Rademacher
weights, 10,000 replicates, seed fixed in the reproducibility manifest) with
the statistic defined below. A secondary sensitivity uses a symbol-and-block
cluster-robust sandwich estimator; no result is eligible if the primary and
secondary procedures are not both executable. No block may cross a segment
gap. If a horizon is later supplied, a Newey–West lag of
`ceil(h / 15 minutes) - 1` is recorded only as a sensitivity, never searched.

The family-wise error rate is controlled across exactly six primary hypothesis
tests with Holm step-down at two-sided `alpha = 0.05` (for H03/H04 the
predeclared directional alternative is reported, but the two-sided statistic
is retained for the family gate). No threshold, horizon, feature, or
subgroup variants may be added after this amendment.

## 3. Frozen estimands

The following equations define the complete primary family. They are
parameterized by the still-missing single key `h`; this does not authorize any
evaluation until `h` is supplied and hashed.

### R3_H01 — execution-quality context

At an eligible decision, let

\[
s_{i,t}=10^4(ask-bid)/mid,\qquad
m_{i,t}=(ask\,bidQty+bid\,askQty)/(bidQty+askQty),\\
d_{i,t}=(m_{i,t}-mid)/mid.
\]

The primary estimand is the two-component slope vector
`theta_H01(h) = (Cov(Y,s), Cov(Y,d))`, estimated by the predeclared
block-clustered linear projection of `Y` on `(s,d)` and an intercept. This is
two-sided; H01 is context only and never a standalone entry rule.

### R3_H02 — price × open-interest quadrant

\[
q_{i,t}=(sign(C_{i,t}-C_{i,t-1}),\ sign(OI_{i,t}-OI_{i,t-1}))
\in\{(+,+),(+,-),(-,+),(-,-)\}.
\]

Zero or missing components are ineligible. The estimand is the four-cell
conditional-mean vector
`theta_H02(h) = (E[Y | q = cell])_{cell in Q}` together with the omnibus
four-cell equality statistic. The four cells and their order are fixed above;
the test is two-sided and does not pick a reference cell after inspection.

### R3_H03 — liquidation continuation

For each observed force-order event `e`, retain the frozen pressure
`p_e = sign_e * last_filled_quantity_e * average_fill_price_e`, with
`sign_e=+1` for forced `SELL` and `-1` for forced `BUY`. Let
`u_e = -sign_e`, the predeclared price-direction sign (forced sell is `-1`,
forced buy is `+1`). The continuation estimand is

\[
theta_{H03}(h)=E[u_e\,Y_{i(e),t(e),h}\mid e\ observed].
\]

The primary directional alternative is `theta_H03(h) > 0`; the two-sided
bootstrap statistic remains the family statistic. Stream and restart gaps are
not events and cannot be imputed.

### R3_H04 — liquidation reversion

Using the identical event set and `u_e` above, the reversion estimand is

\[
theta_{H04}(h)=E[-u_e\,Y_{i(e),t(e),h}\mid e\ observed].
\]

The primary directional alternative is `theta_H04(h) > 0` (equivalently,
`E[u_e Y] < 0`). It is a distinct preregistered hypothesis, not a polarity
switch chosen from data.

### R3_H05 — crowding × stress modifier

Let `f_{i,t}=lastFundingRate` from `/fapi/v1/premiumIndex` and
`p_{i,t}=close` of the latest completed
`/fapi/v1/premiumIndexKlines?interval=15m`. Let
`b_{i,t}=sign(C_{i,t}-C_{i,t-1})` be the frozen baseline price direction.
Both context components must be available before the next executable open.
The estimand is the two-component modifier vector

\[
theta_{H05}(h)=\big(Cov(bY,f),\ Cov(bY,p)\big).
\]

It is two-sided and modifier-only: neither component creates a standalone
entry, and mark price is never substituted for premium.

### R3_H06 — BTC/breadth concordance

For the frozen selected universe `U_t`,

\[
C_t=|U_t|^{-1}\sum_{j\in U_t}sign(r_{j,t})sign(r_{BTC,t}),
\qquad r_{j,t}=\log(C_{j,t}/C_{j,t-1}).
\]

Symbols without a valid return are removed from the denominator. The
estimand is `theta_H06(h)=Cov(Y_{i,t,h}, C_t)` from the block-clustered
projection of `Y` on `C_t` and an intercept. It is two-sided; BTC is context
only when it is not in the selected Top50.

## 4. Evidence minima and stopping rule

These are fixed operational sufficiency gates, not optimization targets:

| Gate | Frozen requirement |
|---|---|
| Calendar span | at least 30 complete UTC calendar days after the first eligible cycle |
| Independent dependence units | at least 120 complete UTC six-hour blocks |
| Roster diversity | at least two distinct roster months, each with a verified roster hash |
| H01 | at least 5,000 eligible book-ticker observations |
| H02 | at least 5,000 eligible symbol quadrant observations |
| H03 | at least 1,000 observed force-order events with eligible responses |
| H04 | the same 1,000-event floor, counted independently |
| H05 | at least 5,000 complete funding+premium pairs |
| H06 | at least 5,000 eligible symbol/breadth observations |
| Completeness | zero duplicate/missing cycles, zero strict-boundary violations, and no unresolved source-integrity blocker |

The checker must report each gate separately and fail closed on any unmet gate,
on `H_frozen = ∅`, or on a missing human authorization receipt. Meeting gates
never starts a run automatically. Collection continues until the gates are
met; a human must then authorize a separately versioned evaluation command.

## 5. Immutable firewall

This amendment does not authorize access to any final holdout, R2B2
materialization, forward-label store, return/PnL/Sharpe/hit-rate field,
historical ranking, or performance report. The metadata-only readiness checker
may read only the v8 identity, health, manifest-chain, roster metadata, and
outcome-blind inventory. Any path or key containing a forbidden outcome token
must cause a deterministic failure before evaluation eligibility is reported.

The amendment is frozen before any historical evaluation. Its SHA256 is
recorded in the accompanying reproducibility manifest and in the final
outcome-blind report. A future horizon amendment must supersede this file by
hash; it may not edit this file in place.
