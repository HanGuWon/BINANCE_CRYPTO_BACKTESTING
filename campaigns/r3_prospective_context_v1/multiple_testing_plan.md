# R3 multiple-testing plan

The primary family is exactly six mechanism hypotheses, one row per structural
context mechanism in `trial_registry.csv`. There are no threshold or horizon
grids in the collection campaign. Any later confirmatory analysis must account
for all six hypotheses jointly and may not add variants after observing returns.

`R3_EVALUATION_AMENDMENT_V1.md` is the frozen evaluation contract for these
same six rows. It uses Holm step-down at alpha 0.05 across exactly six primary
tests, with no post-hoc polarity, threshold, horizon, subgroup, or diagnostic
variant. The absence of a pre-existing horizon key is an explicit hard block;
it is not a license to search horizons.
