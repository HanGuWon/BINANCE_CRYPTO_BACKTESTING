# R3 multiple-testing plan — V2 freeze

The primary family is exactly six structural hypotheses (`R3_H01` through
`R3_H06`), one row per mechanism in `trial_registry.csv`. There are no
threshold, horizon, polarity, subgroup, or diagnostic grids. The sole horizon
is `R3_HORIZON_15M_NEXT_NATIVE_BAR_V1`, a native 15-minute one-bar response;
its selection basis is `EX_ANTE_NATIVE_COLLECTION_CADENCE_AND_MECHANISM_ALIGNMENT`.

`R3_EVALUATION_AMENDMENT_V2.md` is the immutable contract for these six rows.
Holm step-down controls two-sided alpha 0.05 across exactly six primary tests.
The primary dependence units are complete UTC six-hour blocks with a fixed
10,000-draw wild Rademacher bootstrap (seed 1729); the symbol-and-block
clustered sandwich is secondary and NW lag is fixed at 0. No post-hoc horizon,
threshold, polarity, subgroup, or diagnostic variant may be added after any
outcome is observed.

The V1 amendment remains preserved byte-for-byte and is superseded only because
it had no frozen horizon and an incompatible lifetime missing-cycle condition;
it is not invalid outcome evidence.
