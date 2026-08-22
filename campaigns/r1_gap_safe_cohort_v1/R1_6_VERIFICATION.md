# R1.6 verification report

## Provenance

- Parent R1.5: `c6ae3416c7dd13f97a55a0596140f05c2c42047f`
- Final implementation source: `c2fd6c3` (selected-panel manifest preservation and quarantine guard)
- Native-1d acquisition code hash: `883117fbf03d06cbb92238a9bc707e6f812bfa13`
- Branch: `research/r1-gap-safe-cohort-v1`
- Campaign cutoff: `2026-08-21T05:00:00Z`

## Gate 1 — implementation and tests

Python 3.11.15 compiled cleanly. The full repository-local suite collected and
passed 70 tests, including direct gap-safe, derivative-semantic, split/purge,
timeframe-reconciliation, cohort, and CLI-path tests. The final rerun is the
release evidence for this report.

## Gates 2–4 — census, taxonomy, and native 1d ranking source

The frozen taxonomy distinguishes CRYPTO, STABLECOIN, FIAT_OR_TOKENIZED_FIAT,
LEVERAGED_OR_SYNTHETIC, DATED_DELIVERY, PERPETUAL_VERIFIED,
PERPETUAL_STYLE_UNVERIFIED, and UNKNOWN. Counts are 657 Spot CRYPTO, 828
verified UM perpetual, 11 stablecoin, 4 fiat/tokenized-fiat, 54
leveraged/synthetic, 50 dated-delivery, and 3,064 unresolved rows. The primary
crypto candidate universe is 1,485 symbols; the all-USDT diagnostic universe is
1,604 symbols.

The prior-completed-calendar-month quote-volume ranking source contains 46,169
native 1d objects (25,713 spot; 20,456 UM), totaling 79,643,414 compressed
bytes. Acquisition completed with 46,124 PASS objects and 45 recorded failures
(30 ERROR, 15 ISSUES; zero checksum mismatches). The estimate was 318,573,656
extracted bytes and 119,465,121 Parquet bytes; free disk was
30,522,241,024 bytes before and 30,135,975,936 bytes after acquisition.

## Gate 5 — causal cohorts

The monthly cohort table contains 187 market-months (108 spot, 79 UM), 8,316
Top-50 membership rows, 33 membership-gap months, and 1,753 partial prior-month
exclusions. Ranking uses only the completed prior calendar month and excludes
partial-month seasoning; no future membership information is used.

## Gates 6–8 — selected panel, gap safety, and timeframe policy

The selected context manifest contains 11,714 native 15m objects (6,322 spot;
5,392 UM), with 8,214 research-eligible and 3,500 warmup-context rows. The
materialized panel contains 32,025,056 15m rows, 8,005,673 1h rows, and
2,000,099 4h rows, with 8,249 causal segments and 5,834 detected gaps.
Research-eligible rows are 29,628,553; warmup-context rows are 12,402,275.

Six symbol groups were quarantined rather than coerced because their historical
source timestamps were off the declared 15m grid: BCCUSDT, BNBUSDT, BTCUSDT,
ETHUSDT, LTCUSDT, and NEOUSDT (all spot). They are listed in
`selected_materialization_failures.csv`.

The native 15m/1h/4h anchor comparison checked 2024-01 and 2024-02 and matched
all declared OHLCV fields within the frozen numerical tolerance. The selected
panel materializer currently derives 1h and 4h from the canonical 15m source;
native higher-timeframe acquisition is therefore a remaining R1 blocker even
though the reconciliation gate itself passed.

The cohort-aware breadth implementation enforces the 0.80 valid-fraction
threshold and emits `INSUFFICIENT_CROSS_SECTION`; full-panel breadth diagnostics
are not used to claim performance or ranking.

## Gate 9 — derivative semantics and provenance

Funding events use actual event timestamps, a backward-as-of feature convention,
and the frozen sign convention `-side * sum(rate)` for a long exposure. Funding
z-scores and metrics schema validation are covered by tests. Daily UM metrics,
bookTicker, and bookDepth are present at their probed paths, but metrics is not
treated as openInterestHist; bookTicker is limited to a 2023–2024 sub-study; and
bookDepth does not expose the exact frozen top-book quantities. Canonical
historical OI and top-book imbalance remain unavailable. The append-only archive
revision registry is initialized and contains no detected revisions.

## Gate 10 — global split and purge metadata

The frozen calendar boundaries are train through 2023-01-01, validation through
2024-11-01, and a held-out period after validation. The target horizon is 24h,
with purge bars 96 (15m), 24 (1h), and 6 (4h), plus one operational embargo bar.
`final_holdout_status=UNTOUCHED` remains enforced.

## Scope and verdict

No indicator performance, Sharpe, IC, MFE/MAE, parameter optimization, or final
holdout access was performed. This is a data-engineering gate only.

**PARTIALLY VERIFIED — R1 BLOCKERS REMAIN**

Remaining blockers are the six quarantined off-grid symbol groups, the lack of
native higher-timeframe acquisition in the selected materializer, and the fact
that breadth is implemented and tested but not a completed performance study.
