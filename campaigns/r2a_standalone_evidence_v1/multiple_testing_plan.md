# Multiple Testing Plan

Testing family: all preregistered trials sharing one market x timeframe cell.
The number of hypotheses per family is fixed by trial_registry.csv BEFORE
the first run and can never grow afterward.

- Primary correction: Benjamini-Hochberg FDR at q = 0.05 per family.
- Secondary report: Bonferroni-adjusted p-values (descriptive only).
- Dependence: p-values derive from HAC/Newey-West statistics; cross-trial
  correlation is addressed by the shared-family FDR and by requiring
  sign-consistent walk-forward folds for promotion.

Any trial added after the first run invalidates the entire family and must be
registered in a NEW campaign with a new split-freeze date.
