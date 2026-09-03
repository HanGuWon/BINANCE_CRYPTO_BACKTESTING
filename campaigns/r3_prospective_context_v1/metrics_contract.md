# R3 metrics contract

This preregistration defines data-quality and later statistical estimands only;
it does not authorize outcome evaluation in this goal. Before any outcome
phase, the evidence window, independent calendar-block minimum, dependence
handling, HAC or block-bootstrap method, and confidence precision target must
be fixed from event counts and resource observations. No return, Sharpe, PnL,
hit-rate, or candidate ranking may be inspected during collection.

The exact six-hypothesis response estimands, missingness, segment-gap and
right-censor rules, 30-day/120-block calendar gates, per-hypothesis input
floors, two-roster-month requirement, and Holm step-down family correction are
frozen in `R3_EVALUATION_AMENDMENT_V1.md`. The response horizon is deliberately
not supplied here: `trial_registry.csv` has no horizon key and no pre-existing
R3 horizon artifact is authoritative. Readiness must therefore fail closed
until a human-approved, hashed single horizon amendment exists. The primary
dependence unit is a complete UTC six-hour block; wild block bootstrap is
primary and symbol-and-block clustered sandwich inference is sensitivity.
