# Phase 1 — deterministic R3 V2 horizon map and scalar estimands

## Unit and safety

This unit supersedes the earlier single-native-15m V2 design without editing
V1 or the earlier V2 bytes. It writes only governance text and the immutable
horizon-map metadata artifact. No response, close, label, return, PnL,
performance, ranking, final-holdout, or R2B2 field may be read or computed.
The D-backed `scientific_raw_v8` collector remains append-only and running.

The current horizon-map bytes are pinned by SHA256
`7cd935a33ac7ed47d1b9c7e037d5033b3add694934730eca5ebadda48fbb98e5`.

## Exact horizon map

The map contains exactly six keys. Every response begins at the first
executable open after all required source fields pass the strict availability
predicate `source_available_time < next_executable_open_time`; equality is an
ineligibility condition. Native 15-minute closed-kline availability is its
close timestamp. A derived 1-hour/4-hour bucket is available only at the
maximum close timestamp of all complete constituent 15-minute bars.

REST snapshots use `corrected_response_receipt_time`, falling back to
`response_received_at`; the latest finite record strictly before `T_exec` is
selected, with `source_identity` as the final tie-break. A forceOrder event
uses normalized-envelope `exchange_event_time` from payload `E`; order `T`/`t`
is descriptive only, and its `T_exec` is the smallest scheduled open strictly
after both event time and corrected collector receipt time.

| key | response key | start | end | source/endpoint | overlap rule |
|---|---|---|---|---|---|
| H01 | `FWD_15M` | `T_exec` | close of the next completed 15m kline (`T_exec+15m`) | closed price kline | independent |
| H02 | `FWD_1H` | `T_exec` | `T_exec+60m` | four complete 15m closes, endpoint at the 1h close | independent |
| H03 | `LIQ_CONT_15M` | `T_exec` | `T_exec+15m` | forceOrder event plus closed price kline | immediate liquidation response |
| H04 | `LIQ_REVERSION_15M_TO_1H` | `T_exec+15m` | `T_exec+60m` | the same event, later closed price endpoint | incremental interval; no overlap with H03 |
| H05 | `FWD_1H` | `T_exec` | `T_exec+60m` | funding snapshot + completed premium kline + price kline | independent |
| H06 | `FWD_1H` | `T_exec` | `T_exec+60m` | price kline plus BTC/breadth context | independent |

`T_exec` is never replaced with source-open time. For H01, the endpoint is
the close of the single completed native 15-minute bar immediately following
`T_exec`, not an interpolated or source-open observation. H02, H05, and H06
share the one-hour window by design but remain separate predeclared
hypotheses; this is not a post-outcome horizon search. H04 is the price change
from +15m to +60m, `log(C_{T_exec+60m}/C_{T_exec+15m})`, and is not the negative
of H03's immediate response.

## One scalar primary test per hypothesis

All models use the fixed UTC-6h complete-block wild-cluster bootstrap: fit the
restricted null, multiply complete-block residuals by the seeded 10,000-draw
Rademacher sequence, refit, and retain the observed studentization. The
inclusive two-sided tail is `(1 + count(|T_boot| >= |T_obs|)) / 10001` with no
rounding. A rank-deficient design, missing H02 cell, non-positive robust
variance, non-finite statistic, or fewer than two complete blocks is
ineligible and fails closed. Exactly one p-value is emitted for each H01–H06.
Component estimates, cell means, contrasts, and diagnostics are
secondary/descriptive and cannot enter the primary family or be selected later.
Holm step-down controls the six primary p-values at two-sided alpha 0.05.

### H01 — execution-quality joint omnibus

At each eligible decision define

`spread_bps = 10^4*(ask-bid)/mid` and
`microprice_displacement = ((ask*bidQty + bid*askQty)/(bidQty+askQty)-mid)/mid`.

Let `D=sign(C_t-C_{t-1})` be the fixed baseline direction and fit the
predeclared block-clustered linear model

`Y_H01 = alpha + gamma*D + beta_s*spread_bps + beta_m*microprice_displacement + error`.

The tested columns must have rank exactly 2 (and the nuisance design full
rank); otherwise the observation set is ineligible. The sole primary statistic
is the two-degree-of-freedom Wald omnibus
`W_H01 = (beta_s,beta_m)' V^{-1}(beta_s,beta_m)` for the joint null
`beta_s=beta_m=0`, with the bootstrap p-value. There are no separate spread or
microprice p-values and no reference direction chosen after inspection.

### H02 — fixed four-cell equality omnibus

Define the fixed quadrant

`Q=(sign(Delta close), sign(Delta open_interest))` in the ordered cells
`(++),(+-),(-+),(--)`; zero/missing components are ineligible. All four cells
must be present and the four-column cell design must have rank 4. Fit a
saturated cell-means model for `Y_H02`. The sole primary statistic is the
three-degree-of-freedom Wald test that all four cell means are equal. The cell
means and pairwise contrasts are secondary/descriptive only; no reference cell
is selected after outcomes.

### H03 — immediate signed continuation

Start from one candidate forceOrder event universe after identity validation
and replay deduplication. H03 retains a candidate only when its event boundary,
source receipt, `T_exec`, and +15m endpoint are finite and complete. Let
`u_e=+1` for a forced BUY and `u_e=-1` for a forced SELL (the frozen
price-direction sign). Define

`Y_e,H03 = log(C_{symbol(e),T_exec+15m}/C_{symbol(e),T_exec})` and
`theta_H03 = E[u_e * Y_e,H03]`.

The sole primary statistic is the one-degree-of-freedom studentized mean of
`u_e*Y_e,H03`; the preregistered directional alternative is `theta_H03>0`,
while the family p-value remains two-sided. No-event, missing, restart, and
rollover records are not zero events.

### H04 — delayed signed reversal, incremental and non-overlapping

Use the same candidate identities and signs as H03, then apply an independent
H04 endpoint filter requiring both +15m and +60m endpoints. Define the
non-overlapping delayed response

`Y_e,H04 = log(C_{symbol(e),T_exec+60m}/C_{symbol(e),T_exec+15m})` and
`theta_H04 = E[-u_e * Y_e,H04]`.

The sole primary statistic is the one-degree-of-freedom studentized mean of
`-u_e*Y_e,H04`, with directional alternative `theta_H04>0` and a two-sided
family p-value. H04 is not an algebraic polarity rewrite of H03: its response
interval starts at +15m, ends at +60m, and requires both endpoints and the
event boundary to be present.

### H05 — fixed funding-premium joint omnibus

Let `f=lastFundingRate` from `/fapi/v1/premiumIndex`, `p=close` of the latest
completed native `/fapi/v1/premiumIndexKlines?interval=15m`, and
`b=sign(C_t-C_{t-1})`. With `Z=b*Y_H05`, fit

`Z = alpha + beta_f*f + beta_p*p + error`.

The tested columns must have rank exactly 2 and the nuisance design full rank;
otherwise the observation set is ineligible. The sole primary statistic is the
two-degree-of-freedom Wald omnibus for `beta_f=beta_p=0`. Funding and premium
component tests are secondary only; no component fishing or mark-price
substitution is allowed.

### H06 — oriented BTC/breadth association

Let `B_t` be the mean of valid selected-symbol return signs, excluding BTC
from the selected universe. Require a finite, nonzero BTC return before
defining `s_BTC=sign(r_BTC)`, and require a non-empty breadth set. A zero or
non-finite BTC return is ineligible, never a zero-filled pseudo-observation.
Define the oriented breadth score `O_t=s_BTC*B_t` and oriented response
`Z_H06=s_BTC*Y_H06`. Fit the fixed one-predictor model

`Z_H06 = alpha + beta_O*O_t + error`.

The sole primary statistic is the one-degree-of-freedom Wald test of
`beta_O=0`, with one two-sided p-value. Orienting both response and breadth
relative to BTC prevents bullish and bearish regimes from cancelling while
preserving divergence (`O_t<0`) as a distinct sign; an unsigned concordance
or an absolute score is prohibited.

## Censoring, gaps, and future-only boundary

Every required source and response endpoint must be complete and strictly
before the untouched confirmatory holdout boundary. A missing source,
incomplete constituent bucket, exact-boundary timestamp, stream/restart gap,
rollover, or absent response censors only the affected H and never imputes a
zero. Gap intervals map to every intersected UTC-6h block, with overlapping
exclusions counted once. H04 additionally rejects any event whose +15m
boundary is unavailable. These rules are metadata contracts only; no future
response materializer is imported or run in this unit.

## Exit evidence

The next phase may begin only after the JSON horizon map contains exactly
H01–H06, its byte SHA is recorded, the new V2 pins that SHA, the old V2 is
preserved as superseded, and a static review confirms six—and only six—primary
p-value slots with the H03/H04 interval distinction and H06 orientation.
