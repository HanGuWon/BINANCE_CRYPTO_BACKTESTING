# R3 evaluation amendment V2 — six-horizon, outcome-blind contract

**Status:** `R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`

**Recorded:** 2026-09-04 KST

**Campaign:** `r3_prospective_context_v1`
**Primary family:** exactly six rows (`R3_H01`–`R3_H06`) from
`trial_registry.csv`

**Horizon map:** `R3_EVALUATION_HORIZON_MAP_V1.json`
**Horizon-map SHA256:** `7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5`

This amendment is a new, pre-outcome contract. It preserves the bytes of V1
(SHA256 `27276b4d3b66d25c987fadbac531df3cfd741dbd43625406fdc342e89c2f1c39`)
and supersedes the earlier single-native-15m V2 (SHA256
`8f12263c107e8b1fb2596c72f5c3e0c741a17339a42f95aab67df86b87738c38`) because
that design did not define the required six response windows. Neither prior
amendment contains outcome evidence. Their files remain preserved and are not
edited in place.

No response, close, label, return, PnL, ranking, performance, final-holdout,
or R2B2 field is read or computed by this amendment. The sealed v8 collector
continues append-only under its existing implementation, registry, and
source-tree identities.

## 1. Frozen timing and six exact response windows

The authoritative map contains exactly H01–H06 and no alternatives. For every
hypothesis, `T_exec` is the first executable open after all required sources
are available under the strict point-in-time rule

`source_available_time < next_executable_open_time`.

Native 15-minute premium and price klines become available at their completed
kline close. A derived 1-hour or 4-hour bucket becomes available only at the
maximum close of every complete constituent native 15-minute bar. Equality is
rejected; a source-open timestamp cannot satisfy availability. For REST
snapshots, `source_available_time` is the normalized
`corrected_response_receipt_time` when present, otherwise
`response_received_at`; the latest finite snapshot strictly before `T_exec`
is selected by the ascending tuple
`(source_available_time, exchange_event_time, source_identity)` (the
lexicographically greatest eligible tuple wins). For forceOrder,
`exchange_event_time` is the payload `E` value in the normalized envelope and
`source_available_time` is `corrected_response_receipt_time` when present,
otherwise `collector_receipt_time`; order `T`/`t` is descriptive only.
`T_exec` is the smallest scheduled open satisfying both strict inequalities
`T_exec > exchange_event_time` and `T_exec > source_available_time`.
Missing or non-finite timestamps are ineligible.

| key | response | exact interval | response definition |
|---|---|---|---|
| H01 | `FWD_15M` | `[T_exec, next completed 15m close]` | `log(C[T_exec+15m]/C[T_exec])` |
| H02 | `FWD_1H` | `[T_exec, T_exec+60m]` | `log(C[T_exec+60m]/C[T_exec])` |
| H03 | `LIQ_CONT_15M` | `[T_exec, T_exec+15m]` | `log(C[event,T_exec+15m]/C[event,T_exec])` |
| H04 | `LIQ_REVERSION_15M_TO_1H` | `[T_exec+15m, T_exec+60m]` | `log(C[event,T_exec+60m]/C[event,T_exec+15m])` |
| H05 | `FWD_1H` | `[T_exec, T_exec+60m]` | `log(C[T_exec+60m]/C[T_exec])` |
| H06 | `FWD_1H` | `[T_exec, T_exec+60m]` | `log(C[T_exec+60m]/C[T_exec])` |

H04 is incremental and non-overlapping with H03. Its +15m endpoint is the
start of its response interval, not an algebraic sign change of H03. H02,
H05, and H06 intentionally share the one-hour response window but remain
separate predeclared mechanisms. No horizon, endpoint, threshold, or subgroup
may be chosen after outcomes.

## 2. One scalar primary p-value for each H01–H06

The primary dependence unit is a complete UTC six-hour block. For every H,
fit the restricted null model, multiply its complete-block residuals by the
same deterministic Rademacher draw sequence (10,000 draws, seed 1729),
refit the declared statistic, and retain the observed robust studentization.
The inclusive two-sided tail is exactly
`(1 + count(|T_boot| >= |T_obs|)) / 10001`; no p-value rounding or one-sided
switch is permitted. A tested design with rank below its declared rank, a
missing H02 cell, non-positive robust variance, non-finite statistic, or
fewer than two complete blocks is ineligible and fails closed rather than
emitting a sentinel p-value. The secondary sensitivity is a symbol-plus-block
cluster-robust sandwich. Holm step-down controls exactly six two-sided primary
p-values at alpha 0.05. Every vector component, cell contrast, or directional
estimate not named below is secondary/descriptive and cannot be promoted into
the primary family.

### H01 — execution-quality joint omnibus

At an eligible decision, define

`spread_bps = 10^4*(ask-bid)/mid`,

`microprice_displacement = ((ask*bidQty + bid*askQty)/(bidQty+askQty)-mid)/mid`,

and baseline direction `D=sign(C_t-C_{t-1})`. The fixed model is

`Y_H01 = alpha + gamma*D + beta_s*spread_bps + beta_m*microprice_displacement + error`.

The tested design must have full nuisance rank and tested-column rank exactly
2; otherwise the observation set is ineligible. The only primary statistic is
the two-degree-of-freedom Wald omnibus for `H0: beta_s=beta_m=0`, using the
Moore–Penrose covariance only when its tested submatrix has rank 2. Its joint
bootstrap tail area is the one H01 p-value. Separate spread and microprice
p-values are forbidden.

### H02 — four-cell price/open-interest equality omnibus

Define `Q=(sign(Delta close), sign(Delta open_interest))` in the fixed order
`(++),(+-),(-+),(--)`; zero or missing components are ineligible. Every one of
the four cells must be present and the four-column cell design must have rank
4. A saturated cell-means model for `Y_H02` supplies one three-degree-of-
freedom Wald test of equality of all four cell means. Cell means and pairwise
contrasts are secondary/descriptive only; no reference cell is selected after
inspection.

### H03 — immediate liquidation continuation

Start from one candidate forceOrder event universe after deterministic
identity validation and replay deduplication. H03 retains a candidate only
when its event boundary, source receipt, `T_exec`, and +15m endpoint are all
finite and complete. The frozen price-direction sign is `u_e=+1` for forced
BUY and `u_e=-1` for forced SELL. Define

`Y_e,H03 = log(C[event_symbol,T_exec+15m]/C[event_symbol,T_exec])` and
`theta_H03 = E[u_e*Y_e,H03]`.

The sole primary statistic is the studentized mean of `u_e*Y_e,H03`; the
directional alternative is `theta_H03>0`, but its family p-value is two-sided.
No-event, restart, rollover, or missing-event records are not zero events.

### H04 — delayed liquidation reversal

Use the same candidate identities and signs as H03, then apply an independent
H04 endpoint-eligibility filter requiring both the +15m and +60m closed-kline
endpoints. Use the incremental response

`Y_e,H04 = log(C[event_symbol,T_exec+60m]/C[event_symbol,T_exec+15m])` and
`theta_H04 = E[-u_e*Y_e,H04]`.

The sole primary statistic is the studentized mean of `-u_e*Y_e,H04`, with
directional alternative `theta_H04>0` and one two-sided family p-value. H04
requires both endpoints and is not the algebraic negative of H03.

### H05 — funding-premium joint omnibus

Let `f=lastFundingRate` from `/fapi/v1/premiumIndex`, `p=close` of the latest
completed `/fapi/v1/premiumIndexKlines?interval=15m`, and
`b=sign(C_t-C_{t-1})`. With `Z=b*Y_H05`, fit

`Z = alpha + beta_f*f + beta_p*p + error`.

The tested design must have full nuisance rank and tested-column rank exactly
2. The only primary statistic is the two-degree-of-freedom Wald omnibus for
`H0: beta_f=beta_p=0`; funding and premium component tests are secondary.
Mark-price substitution and component fishing are prohibited.

### H06 — oriented BTC/breadth association

Let `B_t` be the mean sign of valid selected-symbol returns, excluding BTC,
and require a finite, nonzero BTC return before defining `s_BTC=sign(r_BTC)`.
If BTC return is zero/non-finite or the selected-symbol breadth set is empty,
the H06 observation is ineligible (never a zero-filled pseudo-observation).
Define the relative-concordance score `O_t=s_BTC*B_t` and the oriented
response `Z_H06=s_BTC*Y_H06`. The fixed model is

`Z_H06 = alpha + beta_O*O_t + error`.

The only primary statistic is the one-degree-of-freedom Wald test of
`H0: beta_O=0`, yielding one two-sided p-value. The orientation keeps bullish
and bearish regimes from cancelling while retaining divergence as `O_t<0`;
an unsigned or absolute concordance is not admissible.

## 3. Missingness, censoring, and gap accounting

Required sources and response endpoints must be complete and strictly before
the untouched confirmatory holdout boundary. A missing component, incomplete
constituent bucket, exact-boundary timestamp, restart/source/rollover gap, or
right-censored response excludes only the affected hypothesis observation.
Nothing is forward-filled, zero-filled, backfilled, or repaired with future
data. Every gap interval maps to every intersected UTC six-hour block, with
overlapping exclusions counted once and source/hypothesis scope retained.

The event identity and replay-safe forceOrder deduplication key are pinned by
the companion identity amendment before qualification; raw and unique counts
are always reported and minima use unique identities. H03 and H04 report
their own endpoint-eligible unique counts from the shared candidate universe.
A no-event interval is
`NO_FORCEORDER_EVENT_OBSERVED`, never a zero signal.

## 4. Evaluation versus untouched confirmatory holdout

The evaluation partition consists only of eligible pre-holdout cycles in the
sealed R3 prospective campaign and is not derived from, or merged with, any
R2A or R2B partition. The confirmatory holdout is the separately sealed,
untouched post-boundary partition. It cannot complete a response, a gap block,
an evidence minimum, or a primary test. Access requires a future, separately
versioned human authorization; this amendment does not grant it.

## 5. Readiness and execution firewall

A metadata-only readiness checker may inspect only the amendment/map hashes,
registry and source identities, cycle/health/manifest metadata, roster
identities, explicit gap/block accounting, and outcome-blind inventory. It must
assert exactly six primary p-values, reject hidden component tests, verify all
per-H and global minima, and require explicit human authorization before any
future evaluation command. The checker must not import or call a response
materializer.

Meeting metadata minima never starts evaluation automatically. Until minima,
integrity, and authorization all pass, the state remains
`R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`. This file, the horizon map,
and all receipts are append-only; a later contract supersedes them by hash and
does not rewrite prior evidence.
