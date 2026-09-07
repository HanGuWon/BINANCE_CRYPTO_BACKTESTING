# R2A.1 Corrective Verification — Re-execution Under the Original Preregistration

Verdict: **VERIFIED — R2A CORRECTED, PRIOR POSITIVE EVIDENCE DID NOT SURVIVE**

## Provenance chain

- Original preregistration SHA: dd4f0011519575f5474ba759d5764a7d27d5db66
- Pre-outcome amendment SHA: 801cde50ec661d8c65cfa9ed7af76b42aa3c48fd (252-trial registry frozen)
- Erratum SHA (this correction): see R2A_ERRATUM_001.md commit below
- Corrected implementation / corrected outcome SHA: the R2A.1 corrective commit
  a051eeeceae9cee34ee4a0150e94de51e6747747; engine fixes + rerun + re-aggregation landed together after the
  superseded run was archived, so no superseded outcome could inform it)
- Superseded outcome artifacts: campaigns/r2a_standalone_evidence_v1/
  superseded_outcomes_v0/ with SHA256SUMS.txt; superseded checkpoints on D:
  under r2a/checkpoints_superseded_v0/. Nothing silently overwritten.

## Trial accounting

- 252 / 252 trials completed; failed=0; censored=0
- Families unchanged: spot|15m=27 spot|1h=26 spot|4h=27 um|15m=58 um|1h=56 um|4h=58

## Corrections applied and their impact

- Next-open fix (entry = decision+1, embargo no longer delays trades): shifted
  every entry/exit by one bar; changed all trade-level returns in Spot AND UM.
- Funding sign fix (+funding_cashflow = -side*sum(crossed rates)): changes every
  UM net return. LONG positive funding now pays, SHORT positive funding now
  receives, as required.
- Impact: the previous run's Grade A candidates (T0048 Spot 1h, T0130 UM 1h)
  did not survive. In the corrected run there are NO Grade A or B trials.

## Final grades (validation partition only as primary)

- Grade A: 0    Grade B: 0    Grade C: 73    Grade D: 179
- FDR survivors (q<=0.05): 67 across families, but NONE satisfy the frozen
  promotion criteria for A/B.
- The single prior positive (T0130, previously Grade A in the superseded run) is now Grade C/D territory: its walk-forward
  fold_count is 1, which is explicitly reported as INSUFFICIENT_ROBUSTNESS_EVIDENCE
  (robustness_flags.json lists all 252 trials as having <2 independent folds).
- Concentration failures (top symbol >50% of net contribution): 43 trials flagged;
  none reach A/B so none are promoted regardless.

## Short validation window honesty

- Validation window: approximately 2024-01-20 through 2024-02-08 (~20 calendar days).
- Independent calendar blocks available: 1 (a single ~3-week block).
- Actual walk-forward folds per trial: 1 (or 0 where too few trades); never >=2.
- Annualized Sharpe from this window is DESCRIPTIVE ONLY and was not used as
  standalone evidence of robustness.
- Top20/Top100 diagnostics were materialized as distinct rows in
  cohort_diagnostics.csv for all 252 trials (top20/top50/top100 x 252 rows).

## Holdout guard status (restated honestly)

- Row-groups entirely inside the holdout are skipped via Parquet row-group
  timestamp statistics before reading; straddling groups are read from disk but
  filtered BEFORE pandas conversion.
- PROVEN: no holdout row reaches pandas, signal computation, trade generation,
  statistics, checkpoint outputs, or aggregate artifacts (asserted at load, at
  trial execution, and again in aggregation; regression tests cover rejection).
- NOT CLAIMED: byte-level "never read from disk" for boundary-straddling groups.
- final_holdout outcome exposure = NONE.

## Tests

- compileall: PASS. pytest: **113 passed** (new gates: exact next-open = decision+1,
  embargo never delays trades, LONG/SHORT x positive/negative funding sign matrix,
  non-overlap per symbol on all timeframes, deterministic rerun).

A disappearance of prior Grade A/B evidence is a valid scientific outcome of the
corrective audit: the earlier positives were artifacts of implementation defects,
not of the preregistered design.
