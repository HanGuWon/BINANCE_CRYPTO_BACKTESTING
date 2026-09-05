# R2A Preregistration Amendment 001 (PRE-OUTCOME)

Date: 2026-08-24 (KST), BEFORE any R2A outcome/performance computation.

## Statement

NO R2A outcome was inspected before this correction. The only analyses run
so far are the mechanical eligibility checks below and the R1.7.1 coverage
audit that predates the campaign freeze.

## Corrections

1. Removed three invalid 1h market-breadth trials because 1h breadth is
   FORWARD_SHADOW in feature_availability_final.csv:
   - Spot 1h LONG, UM 1h LONG, UM 1h SHORT.
   Registry reduced from 255 to exactly 252 trials; trial_ids renumbered
   deterministically T0001..T0252 preserving original order.
2. Protocol feature counts corrected to per exact market x timeframe
   eligibility: Spot = 17 R2A-primary feature IDs, UM = 19 where structurally
   available (no 1h breadth anywhere).
3. PRIMARY evidence grading is restricted to the validation partition only;
   train results are descriptive/supporting and never pooled with validation
   for significance.

## Unchanged frozen elements

Split boundaries, purge/embargo, horizons, coarse parameter variants, cost
models, FDR families (market x timeframe), bootstrap scheme and promotion
policy semantics are unchanged from the original freeze commit dd4f001.

## Mechanical verification performed pre-outcome

- every trial feature is R2A_PRIMARY for its exact market x timeframe cell;
- variant exists in the frozen coarse grid semantics;
- side legal per market (Spot: LONG only; UM: LONG/SHORT);
- timeframes native 15m/1h/4h only;
- cohort = top50 for all primary trials;
- no duplicate trials;
- deterministic signal semantics exist per preregistered variant.
