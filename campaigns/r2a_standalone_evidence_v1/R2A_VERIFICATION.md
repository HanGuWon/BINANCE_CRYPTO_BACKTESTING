# R2A Verification - Standalone Indicator Evidence Campaign

Verdict: **VERIFIED — R2A COMPLETED, DEFENSIBLE STANDALONE EVIDENCE FOUND**

## Provenance chain

- R1 source SHA: 26d475da5b3747011a7c488118920bf3fc5950e3 (research/r1-final-panel-v1)
- Preregistration freeze SHA (amendment 001): 801cde50ec661d8c65cfa9ed7af76b42aa3c48fd
- Implementation/outcome SHA: 1b99552ba779f344d23e0d3f60015f25d5f9f1ee
  (engine + runner committed BEFORE outcomes; registry SHA pinned in run manifest)
- Registry SHA-256 at run time: a64aedfea95f2134... (run_manifest.json)
- No trial was added after results were visible. The only post-freeze code change
  during execution was a pyarrow compatibility fix inside the loader predicate
  (same boundary semantics; no outcome had been observed when it landed).

## Trial accounting

- Registered trials: 252 (after pre-outcome amendment removed 3 invalid 1h-breadth trials)
- Completed: 252 / Failed: 0 / Censored: 0
- Families (market x timeframe): spot|15m=27, spot|1h=26, spot|4h=27, um|15m=58, um|1h=56, um|4h=58

## Results summary (validation partition ONLY as primary evidence)

- Grade A (STRONG): 2 — volatility.realized_percentile Spot 1h LONG (T0048) and
  UM 1h LONG (T0130). Both show positive mean net return with HAC |t| >= 3,
  FDR q <= 0.05 within family, and >=75% positive walk-forward folds.
- Grade B (MODERATE): 3 — volatility.atr_natr Spot 4h LONG (T0072),
  momentum.rsi UM 1h LONG (T0125, T0127).
- Grade C (WEAK): 78. Grade D (NO EVIDENCE): 169.
- FDR survivors (q <= 0.05): 52 across families.
- Walk-forward stability: Grade A/B trials required >=60% positive folds;
  the two Grade A trials exceed 75%.
- Concentration failures (top symbol > 50% of net contribution): 64 trials
  flagged; none of them are Grade A/B except as reported in candidate_shortlist.csv.
- Cost sensitivity: costs were frozen preregistration (Spot 10bps+5bps slip per side;
  UM 5bps+5bps); all returns reported NET including actual crossed funding events for UM.

## Holdout guard proof

- Loader uses pyarrow predicate pushdown: rows with timestamp >= holdout boundary
  are never read into memory (holdout_guard_proof.json).
- assert_no_holdout() is enforced on every panel and every trial execution;
  aggregation re-asserts the boundary on all trades before any statistic.
- Regression tests cover rejection of holdout timestamps and exact purge/embargo boundaries.
- final_holdout=UNTOUCHED.

## Tests

- python -m compileall -q src tests scripts: PASS
- pytest: 108 passed (includes R2A registry/execution regression gates), see CI log below

## Git push status

- Branch research/r2a-standalone-evidence-v1 pushed to origin through the outcome commit.

A null-heavy outcome (Grade D majority) is itself an informative scientific result:
most standalone indicator variants do NOT survive causal next-open execution costs
with multiple-testing control. No profitability claim is made or implied.
