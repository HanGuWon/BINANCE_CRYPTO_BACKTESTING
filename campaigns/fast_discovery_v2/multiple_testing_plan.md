# Fast Discovery V2 multiple-testing and preregistration plan

Status: FROZEN BEFORE OUTCOMES

The primary S0 family contains exactly the nine rows in `FEATURE_REGISTRY.csv`.
Each row is screened once under the fixed feature transformation in
`S0_SIGNAL_SEMANTICS.json`; no threshold, horizon, polarity, or parameter search
is introduced after seeing outcomes. Continuous primitives remain continuous and
are not silently turned into binary trades.

The development screen is outcome-blind with respect to strategy returns. It may
materialize causal feature values and aggregate diagnostics only. S0 emits no
trade rows and does not access the final holdout. Any later S1/S2 extension
requires a new append-only amendment and registry SHA before outcomes.

Independent evidence is counted by synchronized UTC calendar-day blocks, not row
counts or synthetic fold identifiers. Gaps create absent blocks and do not bridge
state. The causal availability gate is strict: `source_available_time <
next_executable_open_time`.
