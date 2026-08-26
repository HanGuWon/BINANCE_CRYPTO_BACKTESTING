# R2A.2 Erratum 001 — Invalidated Outcome Run & Corrected Freeze

Date: 2026-08-26 (KST). An independent code audit found P0 defects in the
R2A.2 outcome run that had already started. The run was stopped immediately.

## Defects found

1. PER-SYMBOL STATE LEAKAGE: execute_trial_fold operated across the full
   market panel without per-symbol isolation, so causal rolling/EWM state,
   next_available (non-overlap) state, and even entry/exit fills could cross
   symbol boundaries.
2. MISSING FOLD CAUSAL WARMUP: validation folds computed signals from the
   fold start only; the first ~warmup rows of each fold lacked strictly-prior
   history, so indicator values at fold starts differed from a causal
   full-history computation truncated at that timestamp.
3. REGISTRY INCOMPLETE: Spot market_breadth is R2A_PRIMARY on spot 15m and
   spot 4h per the authoritative availability audit, but the registry omitted
   those breadth horizons (4 x spot 15m horizons + 2 x spot 4h horizons).
4. UNTRACKED RUNNER: scripts/run_r2a2_campaign.py was untracked when the
   invalid run started; outcomes cannot be reproduced from a commit SHA.
5. PERFORMANCE DEFECT: row-loop over full panels for every trial x fold caused
   MemoryError failures and made 6000 units infeasible as implemented.

## Disposition of invalid artifacts

- All existing checkpoints moved to D:/BINANCE_CRYPTO_BACKTESTING_DATA/r2a2/
  checkpoints_invalid_superseded_v0/ with SHA256SUMS.txt and an INVALID flag.
- They are preserved for audit lineage but are NOT scientific evidence.

## Corrected preregistration freeze

- Registry regenerated mechanically from R1 authoritative availability with
  spot breadth horizons added: expected exactly 756 trials.
- Corrected runner committed BEFORE any corrected outcome run; run manifest
  pins both registry SHA256 and implementation commit SHA.
- Full run uses a NEW checkpoint root; never resumes invalid checkpoints.
