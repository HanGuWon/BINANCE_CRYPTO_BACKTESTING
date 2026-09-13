# WP25 preparation — causal membership screen input

The development-screen loader now requires `campaigns/r1_gap_safe_cohort_v1/universe_monthly.csv`, filters by market, joins `universe_month` and `symbol`, and excludes non-selected Top50 rows with an explicit count and source SHA in the receipt. Missing/duplicate membership is fail-closed. Existing development screen roots are preserved; post-fix screens must use a new versioned output root.

Synthetic verification: 11 loader/Fast Discovery tests passed. Historical development screening is authorized only after this committed source state; final holdout, R2B2, and R3 remain excluded.
