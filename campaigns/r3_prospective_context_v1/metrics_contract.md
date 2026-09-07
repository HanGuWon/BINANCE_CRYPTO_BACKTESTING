# R3 metrics contract — evaluation amendment v2

This preregistration defines data-quality gates and later statistical estimands;
it does not authorize outcome evaluation during collection. The immutable
contract is `R3_EVALUATION_AMENDMENT_V2.md` and the sole horizon is
`R3_HORIZON_15M_NEXT_NATIVE_BAR_V1` (`15m`, one bar, no alternatives).

The symbolic response interval is `[T_exec, T_exec + 15m]`, where `T_exec` is
the next executable native 15-minute open. The strict causal rule is
`source_available_time < next_executable_open_time`; equality is rejected.
Native premium-index 15-minute availability is the native kline close. A
derived 1-hour/4-hour bucket is available at the maximum close of all complete
constituent native bars. A source-open timestamp, mark price, or response
receipt cannot substitute for this availability time.

The six exact estimands, missingness, segment-gap and right-censor rules,
30-day/120-complete-UTC-6h-block gates, per-hypothesis floors, two verified
roster-month requirement, and Holm step-down correction are frozen in V2. Raw
counts are descriptive; explicit restart/source/missing/rollover gaps map to
all intersected UTC six-hour blocks, and affected primary observations/events
are ineligible once per block. No aggregate gap-count subtraction, imputation,
or backfill is permitted.

The primary dependence unit is a complete UTC six-hour block. Inference is a
10,000-replicate wild Rademacher block bootstrap with seed 1729; symbol-and-
block clustered sandwich inference is secondary. The fixed Newey–West
sensitivity lag is `ceil(15m/15m)-1 = 0`. Holm step-down controls the two-sided
family-wise error rate at alpha 0.05 across exactly H01–H06.

Readiness is metadata-only. A frozen contract with unmet minima reports
`R3_EVALUATION_PREREGISTERED_COLLECTION_CONTINUES`; an integrity or contract
failure reports `R3_EVALUATION_PREREGISTRATION_BLOCKED`. Even with all minima,
`evaluation_human_authorized` must be separately true before any evaluation can
start.
