# R2B restricted derivatives v1 — historical pre-holdout outcome report

Status: `INVALID/SUPERSEDED — EXECUTION MEMBERSHIP-GAP CONTINUITY DEFECT`

This v6 report is retained for historical provenance only. It is superseded by
`R2B_CORRECTED_HISTORICAL_OUTCOME_REPORT_2026-08-28.md` after the independent
v6 execution-gap audit documented in `R2B_EXECUTION_ERRATUM_003.md`.

The preregistered 72-row UM family was executed once over the eight frozen
half-year UTC folds. No final-holdout or January-2024 observation was used.
No feature, horizon, polarity, threshold, or strategy combination was changed
after the launch freeze.

## Frozen identities

* Branch: `research/r2b-restricted-derivatives-v1`
* Final HEAD: `5ee5cee` (metadata/report commits after the pinned executable; scientific source tree remains unchanged)
* Implementation commit: `ac9ef2cda9f0571a5902d55aee8bbaa427b190a7`
* Scientific source-tree SHA256 (scripts/src/tests/configs; caches excluded): `11e476ad2b35d2a42ed55afe83a7bf06c68024929aaf1c4aa1cc10b30ce56306`
* Trial registry SHA256: `3c61d923fe2cf88714c8cd2592264800ef2880db894dd2a21170fdf4fcc85302` (72 rows)
* Causal root: `D:\BINANCE_CRYPTO_BACKTESTING_DATA\processed\r2b_restricted_derivatives_v1_repaired_v2_causal3`
* Causal-root SHA256: `6eef4e59225cb45c2833452a883249b11f03469298c1ecfb3837c5f4aaa27a7d` (1,467 partitions; 8,357,398 rows)

## Execution and sealing

Canonical checkpoint root:
`D:\BINANCE_CRYPTO_BACKTESTING_DATA\r2b_restricted_derivatives_v1_checkpoints_v6`

`run_manifest.json` SHA256: `a47ad4d8f2399f2b8cd93650ec483158cbe1b4a54f2ef318eb65d9cbdd84c5e5`.

`run_manifest.json` records exactly 576/576 terminal units, all `VALID`, with
the launch implementation/source identities pinned. The independent
checkpoint verifier returned `PASS`; every decision/source/entry/exit time is
strictly before `2024-01-01T00:00:00Z`, and final-holdout status is
`UNTOUCHED`.

The earlier v2–v5 roots are retained as `INVALID/SUPERSEDED` provenance roots
because their executable identity or funding-boundary implementation changed;
none was silently resumed.

## Deterministic aggregation

The separate aggregator was run twice. Both outputs have SHA256
`e261909d1be97585e1235f181680bef5f64794c360bf1e92c54c1e772ab9c85d` and record
family size 72, HAC inference, joint calendar-month bootstrap (1,000 samples,
seed 1729), and BH-FDR q=0.05 across all 72 hypotheses.

The complete family was retained. BH q≤0.05 occurred for 52/72 hypotheses;
58/72 met the preregistered ≥75% fold-direction criterion, 69/72 met the
top-symbol share ≤0.50 criterion, and only 24/72 avoided the exact
catastrophic-reversal condition. Because the grading contract requires all
gates jointly, the campaign result is `NULL REPLICATION`, not a promoted
strategy.

## Qualification and tests

* Real-data optimized/slow-reference parity: `PASS` twice, identical output
  SHA `c5113f02ad5547f4aa3bd26c145b25d8d99aa83e907cf17a764745d6caae4969`,
  5,512 records; 15m/1h/4h, LONG/SHORT, all registered horizons, gap
  segment, actual funding plus synthetic positive/negative/none funding.
* Targeted/readiness tests: 26 passed.
* Canonical full pytest receipt: 173 passed, 1 warning, exit code 0; scientific
  source scope clean. The global cxc receipt is separately retained with its
  `dirty=true` value because `.codexclaw` is untracked; it is not used as
  scientific cleanliness evidence.

## Outcome-blind semantics evidence

The two preregistered variants were frozen before outcomes because Binance's
official [Premium Index Kline documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Premium-Index-Kline-Data)
defines the measurement but not a trading polarity, while Binance's
[funding-rate explanation](https://www.binance.com/en/support/faq/detail/360033525031)
describes convergence. Peer-reviewed price-discovery and perpetual-futures
work cited in `R2B_PREMIUM_SEMANTICS_REVIEW_2026-08-27.md` supports both
pressure-continuation and crowding-reversion mechanisms. The frozen equations
are strict zero-centered signs for raw premium and `premium_zscore90`:
`PRESSURE_CONTINUATION: p>0→+1, p<0→-1`; `CROWDING_REVERSION: p>0→-1,
p<0→+1`; zero is no signal and NaN/warmup is no signal.

Final holdout: `UNTOUCHED`. R2B2 and post-outcome tuning: not started.
