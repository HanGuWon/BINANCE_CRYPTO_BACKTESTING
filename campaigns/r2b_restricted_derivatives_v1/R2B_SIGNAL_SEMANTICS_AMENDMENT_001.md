# R2B signal semantics amendment 001 (pre-outcome)

Status: `BLOCKED — REVIEW REQUIRED`
Date: 2026-08-27 KST

This amendment freezes the data contract before any outcome access. The
premium value and 90-observation z-score are descriptive UM context features.
Two ex-ante interpretations remain materially plausible (directional pressure
and crowding/mean reversion), and the frozen source does not resolve their
polarity or provide an exogenous trading threshold. The repository therefore
selects no LONG/SHORT signal rule, no event/state rule, and no threshold here.
No historical performance artifact is consulted. The 36-row registry remains
`UNDEFINED_SIGNAL_SEMANTICS` / `BLOCKED_IMPLEMENTATION`.

Any future proposal must name its polarity, threshold, warmup, missingness,
gap-reset, next-open behavior, and whether it is momentum or contrarian; it
must be reviewed against this amendment and registered before qualification.
Until then the only allowed state is
`R2B_BLOCKED_SIGNAL_SEMANTICS`; no executor, outcome checkpoint, or holdout read
may be started.
