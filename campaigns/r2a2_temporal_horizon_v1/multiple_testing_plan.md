# R2A.2 Multiple Testing Plan

Family = ALL preregistered feature x variant x side x market x timeframe x
horizon trials (the full expanded registry, frozen BEFORE the run). BH-FDR at
q=0.05 primary; Bonferroni descriptive secondary. p-values derive from HAC
statistics on aggregate decision-time portfolio series. Family size is asserted
in tests to match trial_registry.csv row count exactly. Adding hypotheses after
any outcome invalidates the family.
