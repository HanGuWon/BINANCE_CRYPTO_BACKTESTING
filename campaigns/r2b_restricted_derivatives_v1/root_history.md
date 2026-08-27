# R2B root history

| root | disposition | producer | reason |
| --- | --- | --- | --- |
| `data/processed/r1_gap_safe_cohort` | immutable R1 evidence | `scripts/build_r16_selected_panel.py` (R1 branch history) | anchor-only premium availability; retained for historical reproducibility |
| `D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1` | `INVALID/SUPERSEDED` | early uncommitted `materialize_r2b_premium_panel.py` | produced before selected-universe-month filtering was corrected; never used for outcomes |
| `D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1_repaired` | `INVALID/SUPERSEDED` | pre-causal `scripts/materialize_r2b_premium_panel.py`; tree SHA256 `03141f3b43aa4d7b68e5a04364fe951ff9a22dc7875299cf57388a1564db5fa4` | source-open alignment admitted observations not yet available at executable open; preserved unchanged |
| `D:/BINANCE_CRYPTO_BACKTESTING_DATA/processed/r2b_restricted_derivatives_v1_repaired_v2_causal3` | canonical causal R2B pre-outcome root | `c19877b` materialization plus independent verifier | 1,467 partitions / 8,357,398 rows; tree SHA256 `6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d`; strict availability guard PASS; no outcome/holdout access |

The superseded root is preserved for auditability and is not deleted or
relabelled as evidence. No R2B outcome checkpoint exists.
