# R2B multiple-testing plan

The complete preregistered family is the 72 rows in `trial_registry.csv`
(two restricted features × two explicitly named signal variants × three
timeframes × two UM sides × the fixed per-timeframe horizon sets). The prior
36-row blocked registry is preserved as `trial_registry.blocked_v1_20260827.csv`
and is superseded, not deleted. No additional variants, indicators, combinations,
or models may be added after outcomes.

If the implementation blocker is cleared and outcomes are authorized, primary
inference will apply Benjamini–Hochberg FDR at `q=0.05` across this complete
family. Any fold, year, month, availability-episode, concentration, or
LONG/SHORT breakdown is descriptive and cannot redefine the family or promote
a weak result to robust evidence. Cross-symbol dependence is preserved by the
time-indexed aggregate decision-time portfolio unit and calendar-block
bootstrap specified before outcomes.
