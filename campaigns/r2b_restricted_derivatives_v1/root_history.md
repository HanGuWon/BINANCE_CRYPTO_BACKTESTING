# R2B root history

| root | disposition | producer | reason |
| --- | --- | --- | --- |
| `data/processed/r1_gap_safe_cohort` | immutable R1 evidence | `scripts/build_r16_selected_panel.py` (R1 branch history) | anchor-only premium availability; retained for historical reproducibility |
| `D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1` | `INVALID/SUPERSEDED` | early uncommitted `materialize_r2b_premium_panel.py` | produced before selected-universe-month filtering was corrected; never used for outcomes |
| `D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1_repaired` | canonical R2B pre-outcome root | corrected `scripts/materialize_r2b_premium_panel.py` in this campaign commit | selected-month filter, contiguous-bucket resampling, pre-holdout cutoff and backward-as-of join verified |

The superseded root is preserved for auditability and is not deleted or
relabelled as evidence. No R2B outcome checkpoint exists.

