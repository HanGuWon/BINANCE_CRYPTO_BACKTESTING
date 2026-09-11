# Fast Discovery qualification phase

Plan: compare optimized funnel output with a deliberately slow reference on constructed frames. Scope excludes historical outcomes and final holdout.

Files: `tests/test_fast_discovery.py` and a new qualification receipt. The reference recomputes primitive and combination metrics without cache; exact aggregate fields, survivor IDs, and zero trade rows must match. Activation fixtures cover non-empty S0/S1/S2, missing OHLC, cache reuse, two calendar folds, opposite/holdout rejection, and rerun hashes. Verifier: `cxc receipt test --session ... -- powershell ... python -m pytest -q tests/test_fast_discovery.py`; exit 0 and identical hashes on two fresh runs are required.


## Audit reconciliation
The C gate is exact and timestamp-based: compare `feature_id/combination_id`, `status`, `aggregate_delta_log_loss`, `positive_fold_fraction`, `independent_block_count`, `trade_rows`, every compact artifact SHA256, and the final summary. Construct one frame with duplicate rows on one UTC date (expected block count 1) and another spanning two UTC dates (expected 2); fold labels alone are insufficient. The CLI test must fail when either `--dataset-root` or `--split-manifest` is absent, and every qualification input is synthetic/development-only with no outcome or holdout path.
