# R2B signal semantics amendment 001 (pre-outcome)

Status: `BLOCKED — REVIEW REQUIRED`
Date: 2026-08-27 KST

This amendment freezes the data contract before any outcome access. The
premium value and 90-observation z-score are descriptive UM context features.
The repository currently has no validated directional polarity, threshold, or
event/state rule for either feature. Therefore no LONG/SHORT signal rule is
selected here, no historical performance artifact is consulted, and the 36-row
registry remains `UNDEFINED_SIGNAL_SEMANTICS` / `BLOCKED_IMPLEMENTATION`.

Any future proposal must name its polarity, threshold, warmup, missingness,
gap-reset, and next-open behavior, be reviewed against this amendment, and be
registered before qualification. Until then the only allowed state is
`R2B_BLOCKED_SIGNAL_SEMANTICS`; no executor, outcome checkpoint, or holdout read
may be started.
