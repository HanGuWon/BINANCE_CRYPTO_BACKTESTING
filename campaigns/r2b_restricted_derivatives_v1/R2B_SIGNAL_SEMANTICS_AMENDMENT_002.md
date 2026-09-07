# R2B signal semantics amendment 002 (pre-outcome freeze)

Date: 2026-08-27 KST  
Status: `FROZEN FOR SYNTHETIC QUALIFICATION — NO HISTORICAL OUTCOMES`
Supersedes: `R2B_SIGNAL_SEMANTICS_AMENDMENT_001.md` (blocked, preserved)

## Hypothesis family

The outcome-blind review found two economically plausible mechanisms and no
exogenous basis for selecting one polarity. Both are therefore preregistered as
distinct variants. The old 36-row blocked registry SHA256 was
`8c302f31a54ccf783010f48a7e964c4ce6871ac8757965dde603b029f2ef0238`. The new
deterministic registry contains 72 UM rows (two features × two variants × three
timeframes × two sides × fixed horizons). Its SHA256 is recorded in the
reproducibility manifest after generation.

Variants:

* `PRESSURE_CONTINUATION`: premium sign is interpreted as same-direction
  derivatives-side pressure.
* `CROWDING_REVERSION`: premium sign is interpreted as the opposite-direction
  convergence/crowding signal.

## Exact signal equations

For either input `x_t`, where `x_t` is respectively the raw `premium` column or
the segment-local `premium_zscore90` column, and `v` is the variant:

```text
pressure(x_t)  = +1 if x_t > 0; -1 if x_t < 0; 0 if x_t == 0
reversion(x_t) = -1 if x_t > 0; +1 if x_t < 0; 0 if x_t == 0
signal_v(x_t)  = pressure(x_t) for PRESSURE_CONTINUATION
                 = reversion(x_t) for CROWDING_REVERSION
NaN, missing, or warmup -> NO_SIGNAL (not a numeric zero; execution gate rejects)
```

The comparison is strict around zero; there is no magnitude threshold and no
crossing/event detector. Each finite observation is a state signal. `+1` means
LONG-eligible direction, `-1` means SHORT-eligible direction, and `0` means no
entry. An executor may open a LONG only when `signal == +1`, and a SHORT only
when `signal == -1`; opposite signs, zero, and NaN never enter.

## Input, warmup, and segmentation

* `derivatives.premium` uses the causal raw premium observation directly.
* `derivatives.premium_zscore` uses the materialized `premium_zscore90` value
  computed from the symbol's own prior 90 observations within the current causal
  segment. No cross-symbol or cross-segment state is allowed.
* Z-score warmup and zero-variance rows are `NO_SIGNAL`.
* A gap/segment boundary resets rolling state; observations before the boundary
  cannot change signals after it.
* Missing premium is not imputed and cannot become zero.
* Appending future observations cannot alter any prior signal.

## Execution and persistence

The signal is evaluated at the causal decision time. Execution remains next-open,
with existing per-symbol non-overlap, funding cashflow, segment-safe state, and
final-holdout guards. This amendment does not permit re-entry on an opposite sign
while an existing position is open; the existing executor's non-overlap rule
continues to apply. Signal generation itself is state-based, not a crossing rule.

## Scope and multiplicity

The scientific registry is UM-only. Spot is an engine control and is not counted
in the R2B family. The complete family is 72 rows and must be treated as one
multiple-testing family. No threshold, horizon, polarity, or variant may be
selected from outcomes after this freeze.

## Qualification gate

Before any historical outcome is authorized, optimized execution must agree with
an independently written slow reference on synthetic/constructed UM fixtures for
all timeframes, sides, registered horizons, both variants, funding signs, missing
premium, warmup, gaps, next-open timing, and opposite-sign rejection. Required
fields include decision/source availability, signal value, entry/exit, gross return,
funding cashflow, and net return.
