# R1.7 Verification

Verdict: **PARTIALLY VERIFIED — R1 PANEL BLOCKERS REMAIN**

## Provenance

- Branch: `research/r1-final-panel-v1`
- Implementation commit: `16d82eeba081465dd41df4d96fcfc6bd948b2a1e`
- Campaign metadata commit: pending (this commit)
- Remote branch: `origin/research/r1-final-panel-v1` (implementation pushed)
- Python: 3.11 (uv-managed runtime)
- Final holdout: `UNTOUCHED`

## Verification gates

- `python -m compileall -q src tests scripts`: PASS
- `pytest --collect-only -q`: 75 tests collected
- `pytest -q`: 75 passed, 1 warning
- Real post-2025 Spot evidence: `BTCUSDT-1d-2025-02.zip` normalized to 28 rows / 28 observed days / `PASS`; no false `MISSING_INTERVAL`.
- Synthetic timestamp proof: `1735689600000` and `1735689600000000` both normalize to `2025-01-01T00:00:00Z` using millisecond and microsecond inference respectively.

## Strict 1d verification

- Listed objects: 46,169
- Verified: 46,124
- Excluded: 45
- Exclusions: 30 `OTHER_REAL_FAILURE` (archive acquisition errors) and 15 `PARTIAL_LISTING_MONTH`; no exclusion was caused by post-2025 Spot microsecond timestamps.
- Canonical classified file: `volume_ranking_exclusions_final.csv`.

## Corrected cohorts

- Before membership hash: `2a3e1466c4f12fc30be46e84626ed3d03fd4fe107a06d5c25b6aaeea0125c4da`
- Rebuilt membership hash: `7f650cfb0a09f32796762804dce750fdc2bb9b9f4d97a5b538b175309c7a72c9`
- Spot: 107 selected months / 407 distinct selected symbols.
- UM: 78 selected months / 404 distinct selected symbols.
- Mature months with Top50 shortfall: 0. The prior five zero-count mature Spot months were invalidated and recovered after timestamp normalization.

## Off-grid quarantine

Six audited Spot symbols (`BCCUSDT`, `BNBUSDT`, `BTCUSDT`, `ETHUSDT`, `LTCUSDT`, `NEOUSDT`) each have one contiguous February-2018 off-grid run of 81 rows. The canonical return-to-grid row at `2018-02-10T06:15:00Z` is preserved. Quarantine is fail-closed and never snaps timestamps. See `off_grid_anomalies.csv`.

## Split proof

With 24-hour purge and one operational embargo bar, exact boundaries are asserted for 15m/1h/4h in tests. Example 15m proof: last train `2024-01-18T23:45Z`, first validation `2024-01-20T00:15Z`, last validation `2024-02-08T23:45Z`, first test `2024-02-10T00:15Z`. Equivalent 1h and 4h assertions are included.

## Blockers / scope

The implementation contains native 15m/1h/4h request and materializer paths, causal BTC context, cohort-aware breadth, event-level funding, and premium helpers. The final campaign rerun did not complete all three native timeframe acquisitions and end-to-end joins after the implementation commit; therefore native panel row/segment counts and feature coverage are not promoted to `R2A_PRIMARY`. No R2A performance analysis or holdout metric was run.

## Free disk and Git

- Last observed free disk before cleanup: approximately 15.7 GB.
- Implementation commit was pushed successfully to GitHub. This report and the small verification artifacts are the only additional campaign files intended for Git; raw archives, Parquet, pickle manifests, and temporary logs remain untracked/excluded.
