# R2A Erratum 001 — Post-Outcome Implementation Deviations

Date: 2026-08-25 (KST). An independent code audit performed AFTER the first
R2A outcome run found the following implementation deviations from the frozen
preregistration. The preregistered hypotheses, thresholds, sides, cohorts,
horizons, costs, split boundaries and FDR families are UNCHANGED.

## Deviations found

1. NEXT-OPEN EXECUTION: the engine used entry = decision + 1 + operational
   embargo bar, delaying every trade by one bar beyond the canonical
   next-executable-open contract. Operational embargo belongs to SPLIT
   boundaries only; it must never delay an individual trade.
2. UM FUNDING SIGN: funding was subtracted as a "cost" using -side*sum(rates)
   already inside that helper, then subtracted again in net_return, which
   flipped the economic sign for shorts. Correct convention: net = gross - fees
   - slippage + funding_cashflow where funding_cashflow = -side * sum(crossed
   rates). Positive funding reduces LONG and increases SHORT returns.
3. HOLDOUT GUARD CLAIM: the loader read full Parquet tables into memory and
   filtered afterward; calling this "predicate pushdown" was inaccurate. The
   corrected implementation pre-scans timestamps per row-group before any row
   is converted to pandas, and the guard claim is restated honestly below.
4. GRADER OVERSTATEMENT: fold_count=1 walk-forward folds were implicitly
   treated as replication evidence; promotion criteria that cannot be
   evaluated from the short validation window must be reported as
   INSUFFICIENT_ROBUSTNESS_EVIDENCE rather than silently passed.
5. MISSING PREREGISTERED DIAGNOSTICS: Top20/Top100 diagnostics required by
   promotion_policy.md for candidates were not materialized as separate rows.

## Scientific handling

- Because next-open timing affects Spot+UM and the funding sign affects UM, ALL
  previous outcome artifacts are invalidated for scientific purposes.
- Superseded outcomes are archived with SHA-256 hashes under
  campaigns/r2a_standalone_evidence_v1/superseded_outcomes_v0/ (hashes recorded;
  bulk checkpoints remain on D: under r2a/checkpoints_superseded_v0/). History
  is preserved; nothing is silently overwritten.
- All 252 trials are re-executed from the corrected implementation.

No outcome from the superseded run informed any correction above: each fix
restores the preregistered semantics exactly as frozen (next-open execution and
the funding convention were both stated in campaign_spec.toml / cost_model.md
before the first run).
